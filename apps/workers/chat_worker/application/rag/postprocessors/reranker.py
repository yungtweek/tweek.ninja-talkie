"""LLM-based reranker postprocessor.

This module is intentionally *lightweight* (single file, minimal abstraction).
It expects candidates to look like LangChain `Document` objects:
- `page_content: str`
- `metadata: dict`

It will add `metadata["rerank_score"]` and `metadata["rerank_reason"]` (optional),
then return documents sorted by rerank_score desc.

Wire your project-specific LLM client in by passing `llm` and implementing
`_call_llm(...)` to match your client interface.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import re
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.runnables import RunnableConfig

from chat_worker.domain.ports.metrics_repo import MetricsRepositoryPort
from chat_worker.infrastructure.langchain.metrics_callback import MetricsCallback

logger = getLogger("Reranker")

def _supports_kwarg(func: Any, name: str) -> bool:
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    if name in sig.parameters:
        return True
    return any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )

class _DocLike(Protocol):
    page_content: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class RerankConfig:
    """Runtime knobs for reranking.

    Keep this small; don't over-abstract yet.
    """

    # Hard cap of how many retrieved candidates we even consider.
    max_candidates: int = 30

    # How many docs to keep after reranking.
    top_n: int = 8

    # LLM call batching (avoid giant prompts).
    batch_size: int = 12

    # Per-doc content trimming (approx chars; adjust to your tokenizer later).
    max_doc_chars: int = 1800

    # Prompt/response controls.
    temperature: float = 0.0
    max_output_tokens: int = 600

    # Safety fallback behavior.
    fail_open: bool = True  # if rerank fails, return input order


class LLMReranker:
    """LLM reranker.

    Usage (conceptually):
        reranker = LLMReranker(llm=rerank_llm, config=RerankConfig(...))
        docs = reranker.rerank(query, docs)

    The `llm` object is intentionally untyped; adapt `_call_llm` to your client.
    """

    def __init__(
        self,
        llm: Any,
        *,
        config: Optional[RerankConfig] = None,
        metrics_repo: MetricsRepositoryPort | None = None,
    ) -> None:
        self._llm = llm
        self._cfg = config or RerankConfig()
        self._metrics_repo = metrics_repo

    def rerank(
        self,
        query: str,
        docs: Sequence[_DocLike],
        *,
        config: Optional[RerankConfig] = None,
        job_id: str | None = None,
    ) -> List[_DocLike]:
        cfg = config or self._cfg

        if not query or not docs:
            return list(docs)

        # 1) Cap candidates.
        candidates: List[_DocLike] = list(docs)[: max(cfg.max_candidates, 0) or 0] or list(docs)
        logger.debug("[RERANK] sync start: in=%s candidates=%s", len(docs), len(candidates))

        # 2) Rerank in batches.
        scored: List[Tuple[_DocLike, float]] = []
        try:
            for batch in _batched(candidates, cfg.batch_size):
                items = self._prepare_items(batch, cfg)
                prompt = _build_prompt(query=query, items=items)
                call_llm = self._call_llm
                if job_id is not None and _supports_kwarg(call_llm, "job_id"):
                    raw = call_llm(prompt, cfg, job_id=job_id)
                else:
                    raw = call_llm(prompt, cfg)
                logger.debug("[RERANK] sync llm raw: %s", _summarize_raw(raw))
                results = _parse_llm_json(raw)
                logger.debug(
                    "[RERANK] sync batch: items=%s results=%s missing=%s",
                    len(items),
                    len(results),
                    max(0, len(items) - len(results)),
                )
                if len(results) == 0:
                    logger.warning("[RERANK] sync parsed 0 results; rerank will be ineffective")

                # Map results to docs by id.
                id_to_doc = {it[0]: it[1] for it in items}  # id -> doc
                for rid, score, reason in results:
                    doc = id_to_doc.get(rid)
                    if doc is None:
                        continue
                    md = _ensure_metadata(doc)
                    try:
                        fscore = float(score)
                    except Exception:
                        fscore = None
                    if fscore is None or not math.isfinite(fscore):
                        md["rerank_score"] = None
                    else:
                        md["rerank_score"] = fscore
                    if reason is not None:
                        md["rerank_reason"] = reason
                    scored.append((doc, md["rerank_score"] if md["rerank_score"] is not None else float("-inf")))

                # Any missing docs in this batch get a very low score but stay.
                missing = set(id_to_doc.keys()) - {rid for rid, _, _ in results}
                if missing:
                    logger.debug("[RERANK] sync missing ids=%s", sorted(missing)[:10])
                for rid in missing:
                    doc = id_to_doc[rid]
                    md = _ensure_metadata(doc)
                    if md.get("rerank_score") is None:
                        md["rerank_score"] = None
                    scored.append((doc, float(md["rerank_score"]) if md["rerank_score"] is not None else float("-inf")))

        except Exception:
            if cfg.fail_open:
                # Fail open: preserve original ordering.
                logger.debug("[RERANK] sync fail_open applied")
                return list(docs)[: cfg.top_n] if cfg.top_n else list(docs)
            raise

        # 3) Global sort & cut.
        scored.sort(key=lambda x: x[1], reverse=True)
        ranked_docs = [d for d, _ in scored]

        # De-dup by object identity (same doc could appear twice if callers pass dupes)
        seen: set[int] = set()
        uniq: List[_DocLike] = []
        for d in ranked_docs:
            oid = id(d)
            if oid in seen:
                continue
            seen.add(oid)
            uniq.append(d)

        if cfg.top_n and cfg.top_n > 0:
            uniq = uniq[: cfg.top_n]

        logger.debug("[RERANK] sync done: out=%s", len(uniq))
        if uniq and all((_ensure_metadata(d).get("rerank_score") in (None, float("-inf"))) for d in uniq):
            logger.warning("[RERANK] sync all rerank_score are -inf/None; output order likely unchanged")
        for i, d in enumerate(uniq, start=1):
            md = _ensure_metadata(d)
            logger.debug(
                "[RERANK][SYNC][%02d] chunk_id=%s score=%s file=%s page=%s",
                i,
                md.get("chunk_id") or md.get("id") or md.get("doc_id"),
                md.get("rerank_score"),
                md.get("filename") or md.get("source"),
                md.get("page"),
            )
        return uniq

    async def arerank(
        self,
        query: str,
        docs: Sequence[_DocLike],
        *,
        config: Optional[RerankConfig] = None,
        job_id: str | None = None,
    ) -> List[_DocLike]:
        cfg = config or self._cfg

        if not query or not docs:
            return list(docs)

        # 1) Cap candidates.
        candidates: List[_DocLike] = list(docs)[: max(cfg.max_candidates, 0) or 0] or list(docs)
        logger.debug("[RERANK] async start: in=%s candidates=%s", len(docs), len(candidates))

        # 2) Rerank in batches.
        scored: List[Tuple[_DocLike, float]] = []
        try:
            for batch in _batched(candidates, cfg.batch_size):
                items = self._prepare_items(batch, cfg)
                prompt = _build_prompt(query=query, items=items)
                call_llm = self._call_llm_async
                if job_id is not None and _supports_kwarg(call_llm, "job_id"):
                    raw = await call_llm(prompt, cfg, job_id=job_id)
                else:
                    raw = await call_llm(prompt, cfg)
                logger.debug("[RERANK] async llm raw: %s", _summarize_raw(raw))
                results = _parse_llm_json(raw)
                logger.debug(
                    "[RERANK] async batch: items=%s results=%s missing=%s",
                    len(items),
                    len(results),
                    max(0, len(items) - len(results)),
                )
                if len(results) == 0:
                    logger.warning("[RERANK] async parsed 0 results; rerank will be ineffective")

                # Map results to docs by id.
                id_to_doc = {it[0]: it[1] for it in items}  # id -> doc
                for rid, score, reason in results:
                    doc = id_to_doc.get(rid)
                    if doc is None:
                        continue
                    md = _ensure_metadata(doc)
                    try:
                        fscore = float(score)
                    except Exception:
                        fscore = None
                    if fscore is None or not math.isfinite(fscore):
                        md["rerank_score"] = None
                    else:
                        md["rerank_score"] = fscore
                    if reason is not None:
                        md["rerank_reason"] = reason
                    scored.append((doc, md["rerank_score"] if md["rerank_score"] is not None else float("-inf")))

                # Any missing docs in this batch get a very low score but stay.
                missing = set(id_to_doc.keys()) - {rid for rid, _, _ in results}
                if missing:
                    logger.debug("[RERANK] async missing ids=%s", sorted(missing)[:10])
                for rid in missing:
                    doc = id_to_doc[rid]
                    md = _ensure_metadata(doc)
                    if md.get("rerank_score") is None:
                        md["rerank_score"] = None
                    scored.append((doc, float(md["rerank_score"]) if md["rerank_score"] is not None else float("-inf")))

        except Exception:
            if cfg.fail_open:
                # Fail open: preserve original ordering.
                logger.debug("[RERANK] async fail_open applied")
                return list(docs)[: cfg.top_n] if cfg.top_n else list(docs)
            raise

        # 3) Global sort & cut.
        scored.sort(key=lambda x: x[1], reverse=True)
        ranked_docs = [d for d, _ in scored]

        # De-dup by object identity (same doc could appear twice if callers pass dupes)
        seen: set[int] = set()
        uniq: List[_DocLike] = []
        for d in ranked_docs:
            oid = id(d)
            if oid in seen:
                continue
            seen.add(oid)
            uniq.append(d)

        if cfg.top_n and cfg.top_n > 0:
            uniq = uniq[: cfg.top_n]

        logger.debug("[RERANK] async done: out=%s", len(uniq))
        if uniq and all((_ensure_metadata(d).get("rerank_score") in (None, float("-inf"))) for d in uniq):
            logger.warning("[RERANK] async all rerank_score are -inf/None; output order likely unchanged")
        for i, d in enumerate(uniq, start=1):
            md = _ensure_metadata(d)
            logger.debug(
                "[RERANK][ASYNC][%02d] chunk_id=%s score=%s file=%s page=%s",
                i,
                md.get("chunk_id") or md.get("id") or md.get("doc_id"),
                md.get("rerank_score"),
                md.get("filename") or md.get("source"),
                md.get("page"),
            )
        return uniq

    def _prepare_items(self, docs: Sequence[_DocLike], cfg: RerankConfig) -> List[Tuple[str, _DocLike, str]]:
        """Return list of (stable_id, doc, preview_text)."""
        items: List[Tuple[str, _DocLike, str]] = []
        used_ids: set[str] = set()
        for i, d in enumerate(docs):
            rid = _doc_id(d, fallback=str(i))
            if rid in used_ids:
                suffix = 1
                candidate = f"{rid}#{suffix}"
                while candidate in used_ids:
                    suffix += 1
                    candidate = f"{rid}#{suffix}"
                rid = candidate
            used_ids.add(rid)
            preview = _trim_text(d.page_content or "", cfg.max_doc_chars)
            items.append((rid, d, preview))
        return items

    def _call_llm(
        self,
        prompt: str,
        cfg: RerankConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        """Call your LLM client and return raw text.

        IMPORTANT: This is a skeleton.
        - If you use LangChain ChatModel: `self._llm.invoke(prompt).content`
        - If you use OpenAI client: `client.responses.create(...).output_text`

        Keep this method tiny and project-specific.
        """
        raise NotImplementedError(
            "Wire your rerank LLM client here. "
            "Return the model's raw text (should be JSON per the prompt)."
        )

    async def _call_llm_async(
        self,
        prompt: str,
        cfg: RerankConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        call_llm = self._call_llm
        if job_id is not None and _supports_kwarg(call_llm, "job_id"):
            return await asyncio.to_thread(call_llm, prompt, cfg, job_id=job_id)
        return await asyncio.to_thread(call_llm, prompt, cfg)


class LangchainReranker(LLMReranker):
    """Reranker backed by a LangChain chat model with sync invoke()."""

    def _call_llm(
        self,
        prompt: str,
        cfg: RerankConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        if not hasattr(self._llm, "invoke"):
            raise RuntimeError("LLM does not support sync invoke() for reranking")
        config = None
        if self._metrics_repo is not None and job_id:
            async def _persist_row(row: dict) -> None:
                await self._metrics_repo.upsert_job(row)

            token_len = lambda s: count_tokens_approximately([s])
            model_name = getattr(self._llm, "model", None) or "unknown"
            provider = getattr(self._llm, "provider", None) or "unknown"
            metric_cb = MetricsCallback(
                job_id=job_id,
                mode="rag",
                span_name="rag_rerank",
                provider=provider,
                model=model_name,
                persist=_persist_row,
                token_len=token_len,
            )
            config = RunnableConfig(callbacks=[metric_cb], tags=["rag_rerank"])
        if config is None:
            result = self._llm.invoke([HumanMessage(content=prompt)])
        else:
            result = self._llm.invoke([HumanMessage(content=prompt)], config=config)
        return getattr(result, "content", result)


class LangchainAsyncReranker(LLMReranker):
    """Reranker backed by a LangChain chat model with async ainvoke()."""

    async def _call_llm_async(
        self,
        prompt: str,
        cfg: RerankConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        if not hasattr(self._llm, "ainvoke"):
            raise RuntimeError("LLM does not support async ainvoke() for reranking")
        config = None
        if self._metrics_repo is not None and job_id:
            async def _persist_row(row: dict) -> None:
                await self._metrics_repo.upsert_job(row)

            token_len = lambda s: count_tokens_approximately([s])
            model_name = getattr(self._llm, "model", None) or "unknown"
            provider = getattr(self._llm, "provider", None) or "unknown"
            metric_cb = MetricsCallback(
                job_id=job_id,
                mode="rag",
                span_name="rag_rerank",
                provider=provider,
                model=model_name,
                persist=_persist_row,
                token_len=token_len,
            )
            config = RunnableConfig(callbacks=[metric_cb], tags=["rag_rerank"])
        if config is None:
            result = await self._llm.ainvoke([HumanMessage(content=prompt)])
        else:
            result = await self._llm.ainvoke([HumanMessage(content=prompt)], config=config)
        return getattr(result, "content", result)


# ---------------------------- helpers ----------------------------


def _batched(xs: Sequence[Any], n: int) -> Iterable[List[Any]]:
    n = max(int(n), 1)
    for i in range(0, len(xs), n):
        yield list(xs[i : i + n])


def _doc_id(doc: _DocLike, *, fallback: str) -> str:
    md = _ensure_metadata(doc)
    for k in ("chunk_id", "id", "doc_id", "source_id"):
        v = md.get(k)
        if v:
            return str(v)
    return fallback


def _trim_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return text
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _summarize_raw(raw: str, max_chars: int = 400) -> str:
    if raw is None:
        return "<None>"
    text = str(raw)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _build_prompt(*, query: str, items: Sequence[Tuple[str, _DocLike, str]]) -> str:
    """Build a strict JSON-output prompt.

    Output must be a JSON array of objects:
      [{"id": "...", "score": 0.0-1.0, "reason": "..."}, ...]

    Score meaning: higher = more directly answers the query.
    """

    # Keep prompt deterministic: no style, no extra chatter.
    header = (
        "You are a reranking engine for retrieval-augmented generation.\n"
        "Given a user query and a list of candidate passages, rank the passages by how directly and specifically they answer the query.\n"
        "Return ONLY valid JSON (no markdown, no commentary).\n\n"
        "Rules:\n"
        "- Prefer passages that contain concrete facts or definitions that answer the query.\n"
        "- Penalize passages that are off-topic, too generic, or only mention filenames/titles without content.\n"
        "- Scores must be between 0 and 1.\n"
        "- Include at most one short sentence for 'reason'.\n\n"
    )

    parts = [header, f"QUERY:\n{query}\n\nCANDIDATES:\n"]

    for idx, (rid, doc, preview) in enumerate(items, start=1):
        md = _ensure_metadata(doc)
        title = md.get("filename") or md.get("title") or md.get("source") or ""
        page = md.get("page")
        loc = f"{title}" if title else ""
        if page is not None:
            loc = f"{loc} p.{page}".strip()

        parts.append(
            "\n".join(
                [
                    f"[{idx}] id={rid}",
                    f"location={loc}" if loc else "location=",
                    f"passage={json.dumps(preview, ensure_ascii=False)}",
                ]
            )
            + "\n"
        )

    parts.append(
        "\nOUTPUT JSON SCHEMA:\n"
        "[\n  {\"id\": \"<candidate id>\", \"score\": <0..1>, \"reason\": \"<short>\"}\n]\n"
        "Return one object per candidate id (same count as input), sorted by score desc.\n"
    )

    return "".join(parts)


def _ensure_metadata(doc: _DocLike) -> Dict[str, Any]:
    md = getattr(doc, "metadata", None)
    if isinstance(md, dict):
        return md
    md = {}
    try:
        doc.metadata = md
    except Exception:
        pass
    return md


def _parse_llm_json(raw: str) -> List[Tuple[str, float, Optional[str]]]:
    """Parse LLM output into [(id, score, reason)].

    Accepts strict JSON. If the model wraps JSON in text, we try to extract the first JSON array.
    """
    if raw is None:
        raise ValueError("Empty reranker output")

    text = raw.strip()

    # Try direct JSON first.
    try:
        data = json.loads(text)
    except Exception:
        # Try to extract a JSON array substring.
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            raise
        data = json.loads(m.group(0))

    if not isinstance(data, list):
        raise ValueError("Reranker output is not a JSON array")

    out: List[Tuple[str, float, Optional[str]]] = []
    for obj in data:
        if not isinstance(obj, dict):
            continue
        rid = obj.get("id")
        score = obj.get("score")
        reason = obj.get("reason")
        if rid is None or score is None:
            continue
        try:
            fscore = float(score)
        except Exception:
            continue
        # Clamp to [0,1] to keep downstream stable.
        fscore = max(0.0, min(1.0, fscore))
        out.append((str(rid), fscore, str(reason) if reason is not None else None))

    return out
