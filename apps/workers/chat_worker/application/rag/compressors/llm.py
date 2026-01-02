

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.runnables import RunnableConfig

from chat_worker.application.rag.document import Document
from chat_worker.domain.ports.metrics_repo import MetricsRepositoryPort
from chat_worker.infrastructure.langchain.metrics_callback import MetricsCallback

logger = getLogger("RagPipeline")

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

@dataclass(frozen=True)
class LLMCompressorConfig:
    """Configuration for LLM-based contextual compression.

    This compressor is intended to be used *after* retrieval/rerank/MMR.

    extract_only:
      If True, instruct the model to only extract verbatim sentences/phrases from the
      provided passage (no rewriting). This is safer for citations.

    per_doc_max_chars:
      Hard cap to keep prompts bounded.

    output_max_chars:
      Hard cap for each compressed output.

    min_keep_chars:
      If compression output is shorter than this and the doc had meaningful content,
      treat it as a failure and fall back to original.

    model:
      Model name/label used by the LLM client.

    temperature, max_output_tokens:
      LLM call parameters (used by client adapter).

    fail_open:
      If True, fall back to original content on LLM errors.

    """

    extract_only: bool = True
    per_doc_max_chars: int = 3500
    output_max_chars: int = 1200
    min_keep_chars: int = 40
    model: str = "llm-compress"
    temperature: float = 0.0
    max_output_tokens: int = 600
    fail_open: bool = True


def _truncate(text: str, max_chars: int) -> str:
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def _doc_text(doc: Document) -> str:
    # Prefer Document's page_content (LangChain-ish) but support common alternatives.
    txt = getattr(doc, "page_content", None)
    if txt is None:
        txt = getattr(doc, "text", None)
    if txt is None:
        txt = ""
    return str(txt)


def _doc_id(doc: Document) -> str:
    md = getattr(doc, "metadata", None) if isinstance(getattr(doc, "metadata", None), dict) else {}
    return str(md.get("chunk_id") or md.get("id") or getattr(doc, "doc_id", None) or "<no-id>")


def _build_prompt(*, query: str, passage: str, extract_only: bool, output_max_chars: int) -> str:
    mode = (
        "Extract verbatim sentences/phrases ONLY. Do not paraphrase or add new facts."
        if extract_only
        else "Compress for relevance. You may lightly rewrite, but must keep facts unchanged."
    )

    return (
        "You are a contextual compressor for RAG.\n"
        "Given a user question and a passage, return only the parts of the passage that are directly useful to answer the question.\n\n"
        f"Rules:\n- {mode}\n- Remove irrelevant lines.\n- Keep output under {output_max_chars} characters.\n- Output MUST be valid JSON with keys: {{\"kept\": string, \"dropped\": number}}.\n\n"
        f"Question:\n{query}\n\n"
        f"Passage:\n{passage}\n"
    )


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        # Common case: model wraps JSON in markdown fences or adds prefix/suffix.
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


class LLMContextualCompressor:
    """LLM-based contextual compression.

    The compressor is intentionally thin. Provide an LLM client or a callable.
    If `llm` is callable, it should accept (prompt, model) or just (prompt).
    Otherwise, override `_call_llm(...)` to adapt your client.
    """

    def __init__(
        self,
        llm: Any,
        cfg: Optional[LLMCompressorConfig] = None,
        metrics_repo: MetricsRepositoryPort | None = None,
    ):
        self._llm = llm
        self.cfg = cfg or LLMCompressorConfig()
        self._metrics_repo = metrics_repo

    def compress_docs(
        self,
        *,
        query: str,
        docs: Sequence[Document],
        job_id: str | None = None,
    ) -> List[Document]:
        if not docs:
            return []

        out: List[Document] = []
        logger.debug("[RAG][llm-compress] start: in=%s model=%s", len(docs), self.cfg.model)

        for idx, doc in enumerate(docs, start=1):
            original = _doc_text(doc)
            passage = _truncate(original, self.cfg.per_doc_max_chars)

            if not passage.strip():
                out.append(doc)
                continue

            prompt = _build_prompt(
                query=query,
                passage=passage,
                extract_only=self.cfg.extract_only,
                output_max_chars=self.cfg.output_max_chars,
            )

            try:
                call_llm = self._call_llm
                if job_id is not None and _supports_kwarg(call_llm, "job_id"):
                    raw = call_llm(prompt, self.cfg, job_id=job_id)
                else:
                    raw = call_llm(prompt, self.cfg)
            except Exception as e:
                if self.cfg.fail_open:
                    logger.warning(
                        "[RAG][llm-compress] llm_call failed: idx=%s id=%s err=%s",
                        idx,
                        _doc_id(doc),
                        repr(e),
                    )
                    out.append(doc)
                    continue
                raise

            payload = _parse_json(raw)
            kept = None
            dropped = None
            if isinstance(payload, dict):
                kept = payload.get("kept")
                dropped = payload.get("dropped")

            kept_text = _truncate(str(kept or "").strip(), self.cfg.output_max_chars)

            # Guardrails: if model returns empty/too short, fall back
            if len(kept_text) < self.cfg.min_keep_chars:
                logger.debug(
                    "[RAG][llm-compress] fallback(original): idx=%s id=%s kept_len=%s raw_len=%s",
                    idx,
                    _doc_id(doc),
                    len(kept_text),
                    len(raw or ""),
                )
                out.append(doc)
                continue

            # Create a new Document preserving metadata, but with compressed text
            md = dict(getattr(doc, "metadata", {}) or {})
            md["compressed"] = True
            md["compressor"] = "llm"
            md["compress_model"] = self.cfg.model
            if dropped is not None:
                try:
                    md["compress_dropped"] = int(dropped)
                except Exception:
                    md["compress_dropped"] = dropped

            try:
                new_doc = Document(page_content=kept_text, metadata=md)
            except Exception:
                # If your Document ctor differs, fall back to mutating the existing doc.
                try:
                    doc.page_content = kept_text
                    doc.metadata = md
                except Exception:
                    pass
                new_doc = doc

            logger.debug(
                "[RAG][llm-compress] ok: idx=%s id=%s orig_len=%s kept_len=%s",
                idx,
                _doc_id(doc),
                len(original),
                len(kept_text),
            )
            out.append(new_doc)

        logger.debug("[RAG][llm-compress] done: out=%s", len(out))
        return out

    async def acompress_docs(
        self,
        *,
        query: str,
        docs: Sequence[Document],
        job_id: str | None = None,
    ) -> List[Document]:
        if not docs:
            return []

        out: List[Document] = []
        logger.debug("[RAG][llm-compress][async] start: in=%s model=%s", len(docs), self.cfg.model)

        for idx, doc in enumerate(docs, start=1):
            original = _doc_text(doc)
            passage = _truncate(original, self.cfg.per_doc_max_chars)

            if not passage.strip():
                out.append(doc)
                continue

            prompt = _build_prompt(
                query=query,
                passage=passage,
                extract_only=self.cfg.extract_only,
                output_max_chars=self.cfg.output_max_chars,
            )

            try:
                call_llm = self._call_llm_async
                if job_id is not None and _supports_kwarg(call_llm, "job_id"):
                    raw = await call_llm(prompt, self.cfg, job_id=job_id)
                else:
                    raw = await call_llm(prompt, self.cfg)
            except Exception as e:
                if self.cfg.fail_open:
                    logger.warning(
                        "[RAG][llm-compress][async] llm_call failed: idx=%s id=%s err=%s",
                        idx,
                        _doc_id(doc),
                        repr(e),
                    )
                    out.append(doc)
                    continue
                raise

            payload = _parse_json(raw)
            kept = None
            dropped = None
            if isinstance(payload, dict):
                kept = payload.get("kept")
                dropped = payload.get("dropped")

            kept_text = _truncate(str(kept or "").strip(), self.cfg.output_max_chars)

            # Guardrails: if model returns empty/too short, fall back
            if len(kept_text) < self.cfg.min_keep_chars:
                logger.debug(
                    "[RAG][llm-compress][async] fallback(original): idx=%s id=%s kept_len=%s raw_len=%s",
                    idx,
                    _doc_id(doc),
                    len(kept_text),
                    len(raw or ""),
                )
                out.append(doc)
                continue

            # Create a new Document preserving metadata, but with compressed text
            md = dict(getattr(doc, "metadata", {}) or {})
            md["compressed"] = True
            md["compressor"] = "llm"
            md["compress_model"] = self.cfg.model
            if dropped is not None:
                try:
                    md["compress_dropped"] = int(dropped)
                except Exception:
                    md["compress_dropped"] = dropped

            try:
                new_doc = Document(page_content=kept_text, metadata=md)
            except Exception:
                # If your Document ctor differs, fall back to mutating the existing doc.
                try:
                    doc.page_content = kept_text
                    doc.metadata = md
                except Exception:
                    pass
                new_doc = doc

            logger.debug(
                "[RAG][llm-compress][async] ok: idx=%s id=%s orig_len=%s kept_len=%s",
                idx,
                _doc_id(doc),
                len(original),
                len(kept_text),
            )
            out.append(new_doc)

        logger.debug("[RAG][llm-compress][async] done: out=%s", len(out))
        return out

    def _call_llm(
        self,
        prompt: str,
        cfg: LLMCompressorConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        """Call your LLM client and return raw text.

        IMPORTANT: This is a skeleton.
        - If you use LangChain ChatModel: `self._llm.invoke([HumanMessage(content=prompt)])`
        - If you use OpenAI client: `client.responses.create(...).output_text`

        Keep this method tiny and project-specific.
        """
        if callable(self._llm):
            try:
                return self._llm(prompt, cfg.model)
            except TypeError:
                return self._llm(prompt)
        raise NotImplementedError(
            "Wire your compressor LLM client here. "
            "Return the model's raw text (should be JSON per the prompt)."
        )

    async def _call_llm_async(
        self,
        prompt: str,
        cfg: LLMCompressorConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        call_llm = self._call_llm
        if job_id is not None and _supports_kwarg(call_llm, "job_id"):
            return await asyncio.to_thread(call_llm, prompt, cfg, job_id=job_id)
        return await asyncio.to_thread(call_llm, prompt, cfg)


class LangchainCompressor(LLMContextualCompressor):
    """Compressor backed by a LangChain chat model with sync invoke()."""

    def _call_llm(
        self,
        prompt: str,
        cfg: LLMCompressorConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        if not hasattr(self._llm, "invoke"):
            raise RuntimeError("LLM does not support sync invoke() for compression")
        config = None
        if self._metrics_repo is not None and job_id:
            async def _persist_row(row: dict) -> None:
                await self._metrics_repo.upsert_job(row)

            token_len = lambda s: count_tokens_approximately([s])
            model_name = getattr(self._llm, "model", None) or cfg.model or "unknown"
            provider = getattr(self._llm, "provider", None) or "unknown"
            metric_cb = MetricsCallback(
                job_id=job_id,
                mode="rag",
                span_name="rag_compress",
                provider=provider,
                model=model_name,
                persist=_persist_row,
                token_len=token_len,
            )
            config = RunnableConfig(callbacks=[metric_cb], tags=["rag_compress"])
        if config is None:
            result = self._llm.invoke([HumanMessage(content=prompt)])
        else:
            result = self._llm.invoke([HumanMessage(content=prompt)], config=config)
        return getattr(result, "content", result)


class LangchainAsyncCompressor(LLMContextualCompressor):
    """Compressor backed by a LangChain chat model with async ainvoke()."""

    def compress_docs(self, *, query: str, docs: Sequence[Document]) -> List[Document]:
        raise RuntimeError("Use acompress_docs() with LangchainAsyncCompressor")

    async def _call_llm_async(
        self,
        prompt: str,
        cfg: LLMCompressorConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        if not hasattr(self._llm, "ainvoke"):
            raise RuntimeError("LLM does not support async ainvoke() for compression")
        config = None
        if self._metrics_repo is not None and job_id:
            async def _persist_row(row: dict) -> None:
                await self._metrics_repo.upsert_job(row)

            token_len = lambda s: count_tokens_approximately([s])
            model_name = getattr(self._llm, "model", None) or cfg.model or "unknown"
            provider = getattr(self._llm, "provider", None) or "unknown"
            metric_cb = MetricsCallback(
                job_id=job_id,
                mode="rag",
                span_name="rag_compress",
                provider=provider,
                model=model_name,
                persist=_persist_row,
                token_len=token_len,
            )
            config = RunnableConfig(callbacks=[metric_cb], tags=["rag_compress"])
        if config is None:
            result = await self._llm.ainvoke([HumanMessage(content=prompt)])
        else:
            result = await self._llm.ainvoke([HumanMessage(content=prompt)], config=config)
        return getattr(result, "content", result)
