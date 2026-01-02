from dataclasses import dataclass, field, replace
from logging import getLogger
import math
from time import monotonic

import weaviate
from typing import Dict, Any, List, Optional, Sequence, cast
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from chat_worker.application.rag.document import Document
from chat_worker.application.rag.helpers import normalize_search_type
from chat_worker.application.rag.helpers.chain import (
    UNSET,
    emit_search_event,
    emit_stage_event,
    expand_queries,
    get_override,
    merge_docs,
    rerank_cfg_value,
    stream_context,
    total_chars,
)
from chat_worker.application.rag.postprocessors.compress_docs import (
    compress_docs as compress_docs_postprocessor,
)
from chat_worker.application.rag.postprocessors.mmr import MMRConfig, MMRPostprocessor
from chat_worker.application.rag.retrievers.base import RagContext, RetrieveResult
from chat_worker.application.rag.retrievers.weaviate_near_text import WeaviateNearTextRetriever
from chat_worker.settings import Settings, RagConfig, WeaviateSearchType
from chat_worker.application.rag.retrievers.weaviate_hybrid import WeaviateHybridRetriever


logger = getLogger("RagPipeline")


@dataclass
class RagState:
    question: str
    rag: Dict[str, Any] = field(default_factory=dict)
    stream: Dict[str, Any] = field(default_factory=dict)
    stream_ctx: Dict[str, Any] = field(default_factory=dict)
    docs: List[Document] = field(default_factory=list)
    reranked_docs: List[Document] = field(default_factory=list)
    mmr_docs: List[Document] = field(default_factory=list)
    compressed_docs: List[Document] = field(default_factory=list)
    heuristic_hits: Optional[int] = None
    llm_applied: Optional[bool] = None
    context: Optional[str] = None
    citations: List[dict[str, Any]] = field(default_factory=list)
    prompt: Any = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_inputs(cls, inputs: "RagState | Dict[str, Any]") -> "RagState":
        if isinstance(inputs, RagState):
            return inputs
        if not isinstance(inputs, dict):
            raise TypeError("RagState inputs must be a dict or RagState")
        question = inputs.get("question")
        if question is None:
            raise KeyError("question")
        known_keys = {
            "question",
            "rag",
            "stream",
            "stream_ctx",
            "docs",
            "reranked_docs",
            "mmr_docs",
            "compressed_docs",
            "heuristic_hits",
            "llm_applied",
            "context",
            "citations",
            "prompt",
            "extra",
        }
        extra = dict(inputs.get("extra") or {})
        for key, value in inputs.items():
            if key in known_keys:
                continue
            extra[key] = value
        return RagState(
            question=question,
            rag=inputs.get("rag") or {},
            stream=inputs.get("stream") or {},
            stream_ctx=inputs.get("stream_ctx") or {},
            docs=list(inputs.get("docs") or []),
            reranked_docs=list(inputs.get("reranked_docs") or []),
            mmr_docs=list(inputs.get("mmr_docs") or []),
            compressed_docs=list(inputs.get("compressed_docs") or []),
            heuristic_hits=inputs.get("heuristic_hits"),
            llm_applied=inputs.get("llm_applied"),
            context=inputs.get("context"),
            citations=list(inputs.get("citations") or []),
            prompt=inputs.get("prompt"),
            extra=extra,
        )

    def copy_with(self, **kwargs: Any) -> "RagState":
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            kwargs["extra"] = {**self.extra, **kwargs["extra"]}
        return replace(self, **kwargs)

    def to_prompt_result(self) -> Dict[str, Any]:
        return {"prompt": self.prompt, "citations": self.citations}

    def to_dict(self, *, include_none: bool = False) -> Dict[str, Any]:
        data = {
            "question": self.question,
            "rag": self.rag,
            "stream": self.stream,
            "stream_ctx": self.stream_ctx,
            "docs": self.docs,
            "reranked_docs": self.reranked_docs,
            "mmr_docs": self.mmr_docs,
            "compressed_docs": self.compressed_docs,
            "heuristic_hits": self.heuristic_hits,
            "llm_applied": self.llm_applied,
            "context": self.context,
            "citations": self.citations,
            "prompt": self.prompt,
            "extra": self.extra,
        }
        if include_none:
            return data
        return {k: v for k, v in data.items() if v is not None}


class RagPipeline:
    """
    RAG pipeline that builds a prompt with retrieved context.

    Uses LangChain core primitives (Runnable, ChatPromptTemplate) together with
    Weaviate-based retrievers (hybrid and near_text) and optional document
    compression. This pipeline prepares the final prompt variables but does not
    call an LLM directly; the caller is responsible for invoking the model.

    Notes:
      - Hybrid search uses dynamic alpha and keyword guards to avoid filename-only bias.
      - Query normalization handles Korean–ASCII boundaries and tech term aliases.
      - Context packing enforces a strict budget while preserving ranking signals.
    """
    try:
        from langchain.retrievers.multi_query import MultiQueryRetriever  # type: ignore
    except Exception:
        MultiQueryRetriever = None  # type: ignore
    WeaviateHybridSearchRetriever = None  # deprecated / unsupported on Weaviate >=1.0

    @staticmethod
    def _extract_docs(result: RetrieveResult | Sequence[Document] | None) -> Sequence[Document]:
        """Normalize retriever outputs into a document sequence."""
        if isinstance(result, dict):
            docs = cast(Sequence[Document], result.get("docs") or [])
        else:
            docs = cast(Sequence[Document], result or [])
        return docs

    def __init__(
            self,
            *,
            settings: RagConfig | None = None,
            collection: str | None = None,
            text_key: str | None = None,
            client: Optional[weaviate.WeaviateClient] = None,
            embeddings: Embeddings,
            default_top_k: int | None = None,
            default_mmq: int | None = None,
            max_context: int | None = None,
            mmr_k: int | None = None,
            mmr_fetch_k: int | None = None,
            mmr_lambda_mult: float | None = None,
            mmr_similarity_threshold: float | None = None,
            search_type: WeaviateSearchType = WeaviateSearchType.HYBRID,
            reranker: Any | None = None,
            llm_compressor: Any | None = None,
    ):
        self.settings = settings or Settings().RAG
        # allow per-instance override via kwargs (take kwargs over settings)
        self.weaviate_url = self.settings.weaviate_url
        self.weaviate_api_key = self.settings.weaviate_api_key
        self.collection = collection or self.settings.collection
        self.text_key = text_key or self.settings.text_key
        self.default_top_k = int(default_top_k or self.settings.top_k)
        self.default_mmq = int(default_mmq or self.settings.mmq)
        self.max_context = int(max_context or self.settings.max_context)
        self.mmr_k = mmr_k if mmr_k is not None else self.settings.mmr_k
        self.mmr_fetch_k = mmr_fetch_k if mmr_fetch_k is not None else self.settings.mmr_fetch_k
        self.mmr_lambda_mult = (
            mmr_lambda_mult if mmr_lambda_mult is not None else self.settings.mmr_lambda_mult
        )
        self.mmr_similarity_threshold = (
            mmr_similarity_threshold
            if mmr_similarity_threshold is not None
            else self.settings.mmr_similarity_threshold
        )
        self.search_type = search_type or self.settings.search_type
        self.alpha = self.settings.alpha
        self.alpha_multi_strong_max = self.settings.alpha_multi_strong_max
        self.alpha_single_strong_min = self.settings.alpha_single_strong_min
        self.alpha_weak_hit_min = self.settings.alpha_weak_hit_min
        self.alpha_no_bm25_min = self.settings.alpha_no_bm25_min
        if isinstance(self.search_type, str):
            self.search_type = WeaviateSearchType(self.search_type.lower())
        self.client = client
        self.embeddings = embeddings
        self.reranker = reranker
        self.llm_compressor = llm_compressor

        # Prompt
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.settings.rag_prompt),
                ("human", "질문: {question}\n\nContext:\n{context}\n\n답변:")
            ]
        )

    async def compress_docs(
        self,
        docs: Sequence[Document],
        query: str,
        *,
        max_context: int | None = None,
        use_llm: bool | None = None,
        job_id: str | None = None,
    ) -> tuple[list[Document], int, bool]:
        """Compress retrieved documents while preserving scores and ranks."""
        if use_llm is None:
            use_llm = self.llm_compressor is not None
        return await compress_docs_postprocessor(
            docs,
            query,
            embeddings=self.embeddings,
            max_context=self.max_context if max_context is None else max_context,
            llm_compressor=self.llm_compressor,
            use_llm=use_llm,
            job_id=job_id,
        )

    async def rerank_docs(
        self,
        docs: Sequence[Document],
        query: str,
        *,
        job_id: str | None = None,
    ) -> list[Document]:
        if self.reranker is None:
            return list(docs)
        try:
            if hasattr(self.reranker, "arerank"):
                reranked = await self.reranker.arerank(query, docs, job_id=job_id)
            else:
                reranked = self.reranker.rerank(query, docs, job_id=job_id)
            return list(reranked)
        except Exception as e:
            logger.warning("[RAG] rerank failed: %s", e)
            return list(docs)

    def join_context(self, docs: List[Document]) -> tuple[str, list[dict[str, Any]]]:
        """
        Pack documents into a single context string with file and section headers.
        Respects the context budget and logs skipped chunks if the budget is exceeded.
        """
        try:
            docs = [Document.from_any(d) for d in docs]
        except Exception:
            docs = [d if isinstance(d, Document) else Document.from_langchain(d) for d in docs]

        buf, total = [], 0
        citations: list[dict[str, Any]] = []
        budget = self.max_context

        def _snippet(text: str, max_chars: int = 240) -> str:
            compact = " ".join((text or "").split())
            if len(compact) <= max_chars:
                return compact
            return compact[: max_chars - 3] + "..."

        def _as_float(val: Any) -> Optional[float]:
            if val is None:
                return None
            try:
                out = float(val)
            except Exception:
                return None
            return out if math.isfinite(out) else None

        for d in docs:
            txt = d.page_content or ""
            title = d.title or (d.metadata.get("filename") if isinstance(d.metadata, dict) else None) or "Untitled"
            section = ""
            md = getattr(d, "metadata", {}) or {}
            if isinstance(md, dict):
                section = md.get("section") or ""

            ln = len(txt)

            try:
                left = (budget - total) if budget is not None else float("inf")
                logger.debug("[RAG][ctx-pack] want=%s left=%s file=%s chunk=%s",
                            ln, left, title,
                            (getattr(d, "chunk_index", None) or (d.metadata.get("chunk_index") if isinstance(d.metadata, dict) else None)))
            except Exception:
                pass

            if budget is not None and total + ln > budget:
                try:
                    left = (budget - total) if budget is not None else float("inf")
                    logger.debug("[RAG][ctx-pack] SKIP due to budget: file=%s chunk=%s need=%s left=%s",
                                title,
                                (getattr(d, "chunk_index", None) or (d.metadata.get("chunk_index") if isinstance(d.metadata, dict) else None)),
                                ln, left)
                except Exception:
                    pass
                continue

            buf.append(f"[{title}]{' > ' + section if section else ''}\n{txt}\n")
            total += ln

            source_id = f"S{len(citations) + 1}"
            chunk_id = (
                d.chunk_id
                or (md.get("chunk_id") if isinstance(md, dict) else None)
                or (md.get("id") if isinstance(md, dict) else None)
                or d.doc_id
            )
            page = d.page if d.page is not None else (md.get("page") if isinstance(md, dict) else None)
            uri = d.uri or (md.get("uri") if isinstance(md, dict) else None) or (md.get("url") if isinstance(md, dict) else None)
            rerank_score = None
            if isinstance(md, dict) and md.get("rerank_score") is not None:
                rerank_score = _as_float(md.get("rerank_score"))
            if rerank_score is None:
                rerank_score = _as_float(md.get("score")) or _as_float(d.score)
            snippet = d.snippet or (md.get("snippet") if isinstance(md, dict) else None) or _snippet(txt)

            citations.append(
                {
                    "id": source_id,
                    "source_id": source_id,
                    "title": title,
                    "file_name": title,
                    "uri": uri,
                    "chunk_id": chunk_id,
                    "page": page,
                    "snippet": snippet,
                    "rerank_score": rerank_score,
                    "score": rerank_score,
                }
            )

        return "\n---\n".join(buf), citations

    def _ensure_state(self, inputs: RagState | Dict[str, Any]) -> RagState:
        return RagState.from_inputs(inputs)

    # ---------------- Retriever/Chain Builder ----------------
    def build_retriever(self, *, top_k: int | None = None, mmq: int | None = None,
                        filters: Dict[str, Any] | None = None,
                        text_key: Optional[str] = None, search_type: Optional[str] = None,
                        alpha: Optional[float] = None):
        """
        Build a retriever based on settings and per-request overrides.
        Supports BM25, Hybrid, near_text, near_vector, similarity, and MMR.
        """
        if self.client is None:
            raise ValueError("Weaviate client must be injected: RagPipeline(client=...)")
        if self.embeddings is None:
            raise ValueError("Embeddings must be injected: RagPipeline(embeddings=...)")

        # Compute effective search type and search kwargs
        st = normalize_search_type(search_type, self.search_type)
        logger.debug(f"[RAG] search_type: {st.value}")
        # Supported modes:
        #   - "hybrid":     Collections API (vector + BM25)
        #   - "near_text":  Collections API (semantic vector search; server-side vectorizer module required, e.g., text2vec-openai; client sends raw text)
        # Notes:
        #   * score_threshold is only respected by "similarity_score_threshold"
        #     (switch search_type if you want a hard cutoff)
        ctx = RagContext(
            client=self.client,
            collection=self.collection,
            embeddings=self.embeddings,
            text_key=(text_key or self.text_key),
            alpha=float(alpha) if alpha is not None else float(self.alpha),
            default_top_k=int(top_k or self.default_top_k),
            mmq=int(mmq) if mmq is not None else None,
            filters=filters,
            settings=self.settings,
        )
        if st == WeaviateSearchType.NEAR_TEXT:
            return WeaviateNearTextRetriever(ctx)
        else:
            return WeaviateHybridRetriever(ctx)

    async def stage_search_call_start(self, inputs: RagState | Dict[str, Any]) -> RagState:
        logger.debug("[RAG] stage_search_call_start")
        state = self._ensure_state(inputs)
        stream_ctx = state.stream_ctx or stream_context({"stream": state.stream})
        state.stream_ctx = stream_ctx
        state.extra.setdefault("search_call_started_at", monotonic())
        if stream_ctx.get("has_stream"):
            await emit_search_event(
                stream_ctx,
                "rag_search_call.in_progress",
                query=state.question,
            )
        return state

    async def stage_retrieve(self, inputs: RagState | Dict[str, Any]) -> RagState:
        logger.debug("[RAG] stage_retrieve")
        state = self._ensure_state(inputs)
        rag_cfg = state.rag or {}
        stream_ctx = state.stream_ctx or stream_context({"stream": state.stream})
        state.stream_ctx = stream_ctx
        q = state.question
        rag_cfg = state.rag or {}
        mmq = int(rag_cfg.get("mmq") or self.default_mmq or 1)
        mmq = max(1, mmq)
        retriever = self.build_retriever(
            top_k=rag_cfg.get("topK"),
            mmq=mmq,
            filters=rag_cfg.get("filters"),
            search_type=rag_cfg.get("searchType"),
            alpha=rag_cfg.get("alpha"),
        )
        started_at = None
        if stream_ctx.get("has_stream"):
            started_at = monotonic()
            await emit_search_event(
                stream_ctx,
                "rag_retrieve.in_progress",
                query=q,
            )
        # Build a fresh retriever for this request and run the initial search.
        def _run_query(query: str) -> Sequence[Document]:
            try:
                result = retriever.invoke(query, mmq=1)
                return self._extract_docs(result)
            except KeyError as e:
                # Handle missing text_key in collection (e.g., 'content' vs 'text'/'page_content')
                candidates = [self.text_key, "text", "page_content", "body", "chunk"]
                last_err = e
                for tk in candidates:
                    if not tk or tk == self.text_key:
                        continue
                    try:
                        retriever2 = self.build_retriever(
                            top_k=rag_cfg.get("topK"),
                            mmq=mmq,
                            filters=rag_cfg.get("filters"),
                            text_key=tk,
                        )
                        fallback_result = retriever2.invoke(query, mmq=1)
                        docs_seq = self._extract_docs(fallback_result)
                        # Success: remember the working text_key for subsequent calls
                        self.text_key = tk
                        return docs_seq
                    except KeyError as ee:
                        last_err = ee
                        continue
                raise last_err

        try:
            logger.debug(
                "[RAG] cfg topK=%s mmq=%s filters=%s",
                rag_cfg.get("topK"),
                mmq,
                rag_cfg.get("filters"),
            )
        except Exception:
            pass

        queries = expand_queries(q, mmq)
        try:
            if mmq > 1:
                logger.info("[RAG] mmq enabled: mmq=%s queries=%s", mmq, len(queries))
                logger.debug("[RAG] mmq variants=%s", queries)
            else:
                logger.debug("[RAG] mmq disabled")
        except Exception:
            pass
        docs_by_query = [_run_query(qv) for qv in queries]
        max_hits = None
        try:
            top_k_value = rag_cfg.get("topK") if rag_cfg.get("topK") is not None else self.default_top_k
            max_hits = int(top_k_value) * len(queries)
        except Exception:
            max_hits = None
        docs = merge_docs(docs_by_query, limit=max_hits)
        if stream_ctx.get("has_stream") and started_at is not None:
            took_ms = int((monotonic() - started_at) * 1000)
            await emit_search_event(
                stream_ctx,
                "rag_retrieve.completed",
                query=q,
                hits=len(docs),
                took_ms=took_ms,
            )
        state.rag = rag_cfg
        state.docs = docs
        return state

    async def stage_rerank(self, inputs: RagState | Dict[str, Any]) -> RagState:
        state = self._ensure_state(inputs)
        q = state.question
        docs = list(state.docs or [])
        stream_ctx = state.stream_ctx or stream_context({"stream": state.stream})
        state.stream_ctx = stream_ctx
        if not docs:
            logger.debug("[RAG] rerank skipped: no docs")
            state.reranked_docs = []
            return state
        rerank_started_at = monotonic()
        if stream_ctx.get("has_stream"):
            await emit_stage_event(
                stream_ctx,
                "rag_rerank.in_progress",
                query=q,
                hits=len(docs),
                input_hits=len(docs),
                input_chars=total_chars(docs),
                reranker=type(self.reranker).__name__ if self.reranker is not None else None,
                rerank_top_n=rerank_cfg_value(self.reranker, "top_n"),
                rerank_max_candidates=rerank_cfg_value(self.reranker, "max_candidates"),
                rerank_batch_size=rerank_cfg_value(self.reranker, "batch_size"),
                rerank_max_doc_chars=rerank_cfg_value(self.reranker, "max_doc_chars"),
            )
        job_id = stream_ctx.get("job_id")
        reranked_docs = await self.rerank_docs(docs, q, job_id=job_id)
        if stream_ctx.get("has_stream"):
            await emit_stage_event(
                stream_ctx,
                "rag_rerank.completed",
                query=q,
                hits=len(reranked_docs),
                input_hits=len(docs),
                output_hits=len(reranked_docs),
                input_chars=total_chars(docs),
                output_chars=total_chars(reranked_docs),
                reranker=type(self.reranker).__name__ if self.reranker is not None else None,
                rerank_top_n=rerank_cfg_value(self.reranker, "top_n"),
                rerank_max_candidates=rerank_cfg_value(self.reranker, "max_candidates"),
                rerank_batch_size=rerank_cfg_value(self.reranker, "batch_size"),
                rerank_max_doc_chars=rerank_cfg_value(self.reranker, "max_doc_chars"),
                took_ms=int((monotonic() - rerank_started_at) * 1000),
            )
        logger.debug("[RAG] reranked_docs: %s", len(reranked_docs))
        state.reranked_docs = reranked_docs
        return state

    async def stage_mmr(self, inputs: RagState | Dict[str, Any]) -> RagState:
        state = self._ensure_state(inputs)
        q = state.question
        rag_cfg = state.rag or {}
        reranked_docs = list(state.reranked_docs or state.docs or [])
        stream_ctx = state.stream_ctx or stream_context({"stream": state.stream})
        state.stream_ctx = stream_ctx
        mmr_docs = reranked_docs
        if not reranked_docs:
            logger.debug("[RAG] mmr skipped: no docs")
            state.mmr_docs = []
            return state
        if reranked_docs:
            try:
                mmr_started_at = monotonic()
                if stream_ctx.get("has_stream"):
                    await emit_stage_event(
                        stream_ctx,
                        "rag_mmr.in_progress",
                        query=q,
                        hits=len(reranked_docs),
                        input_hits=len(reranked_docs),
                        input_chars=total_chars(reranked_docs),
                    )
                mmr_k_raw = get_override(rag_cfg, "mmrK", "mmr_k", default=UNSET)
                if mmr_k_raw is UNSET:
                    mmr_k_raw = self.mmr_k
                if mmr_k_raw is None:
                    mmr_k = len(reranked_docs)
                else:
                    mmr_k = max(0, int(mmr_k_raw))

                mmr_fetch_raw = get_override(rag_cfg, "mmrFetchK", "mmr_fetch_k", default=UNSET)
                if mmr_fetch_raw is UNSET:
                    mmr_fetch_raw = self.mmr_fetch_k
                if mmr_fetch_raw is None:
                    mmr_fetch_k = len(reranked_docs)
                else:
                    mmr_fetch_k = max(0, int(mmr_fetch_raw))
                if mmr_fetch_k < mmr_k:
                    mmr_fetch_k = mmr_k

                mmr_lambda_raw = get_override(rag_cfg, "mmrLambda", "mmr_lambda", default=UNSET)
                if mmr_lambda_raw is UNSET:
                    mmr_lambda_raw = self.mmr_lambda_mult
                mmr_lambda = (
                    float(mmr_lambda_raw)
                    if mmr_lambda_raw is not None
                    else MMRConfig().lambda_mult
                )

                mmr_similarity_raw = get_override(
                    rag_cfg,
                    "mmrSimilarityThreshold",
                    "mmr_similarity_threshold",
                    default=UNSET,
                )
                if mmr_similarity_raw is UNSET:
                    mmr_similarity_raw = self.mmr_similarity_threshold
                if mmr_similarity_raw is UNSET:
                    mmr_similarity = MMRConfig().similarity_threshold
                elif mmr_similarity_raw is None:
                    mmr_similarity = None
                else:
                    mmr_similarity = float(mmr_similarity_raw)

                mmr_cfg = MMRConfig(
                    k=mmr_k,
                    fetch_k=mmr_fetch_k,
                    lambda_mult=mmr_lambda,
                    similarity_threshold=mmr_similarity,
                )
                mmr_docs = MMRPostprocessor(mmr_cfg).apply(query=q, docs=reranked_docs)
                if stream_ctx.get("has_stream"):
                    await emit_stage_event(
                        stream_ctx,
                        "rag_mmr.completed",
                        query=q,
                        hits=len(mmr_docs),
                        input_hits=len(reranked_docs),
                        output_hits=len(mmr_docs),
                        input_chars=total_chars(reranked_docs),
                        output_chars=total_chars(mmr_docs),
                        mmr_k=mmr_cfg.k,
                        mmr_fetch_k=mmr_cfg.fetch_k,
                        mmr_lambda=mmr_cfg.lambda_mult,
                        mmr_similarity_threshold=mmr_cfg.similarity_threshold,
                        took_ms=int((monotonic() - mmr_started_at) * 1000),
                    )
            except Exception as e:
                logger.warning("[RAG] mmr failed: %s", e)
                mmr_docs = reranked_docs
        logger.debug("[RAG] mmr_docs: %s", len(mmr_docs))
        state.mmr_docs = mmr_docs
        return state

    async def stage_compress(self, inputs: RagState | Dict[str, Any]) -> RagState:
        state = self._ensure_state(inputs)
        q = state.question
        rag_cfg = state.rag or {}
        mmr_docs = list(state.mmr_docs or state.reranked_docs or state.docs or [])
        stream_ctx = state.stream_ctx or stream_context({"stream": state.stream})
        state.stream_ctx = stream_ctx
        if not mmr_docs:
            logger.debug("[RAG] compress skipped: no docs")
            state.compressed_docs = []
            state.heuristic_hits = 0
            state.llm_applied = False
            return state
        max_context = get_override(rag_cfg, "maxContext", "max_context", default=UNSET)
        if max_context is UNSET:
            max_context = self.max_context
        if max_context is not None:
            try:
                max_context = int(max_context)
            except Exception:
                max_context = self.max_context
        use_llm_raw = get_override(rag_cfg, "useLlm", "use_llm", default=UNSET)
        if use_llm_raw is UNSET or use_llm_raw is None:
            use_llm = self.llm_compressor is not None
        else:
            use_llm = bool(use_llm_raw)
        compress_started_at = monotonic()
        if stream_ctx.get("has_stream"):
            await emit_stage_event(
                stream_ctx,
                "rag_compress.in_progress",
                query=q,
                hits=len(mmr_docs),
                input_hits=len(mmr_docs),
                input_chars=total_chars(mmr_docs),
                max_context=max_context,
                use_llm=use_llm,
            )
        job_id = stream_ctx.get("job_id")
        compressed_docs, heuristic_hits, llm_applied = await self.compress_docs(
            mmr_docs,
            q,
            max_context=max_context,
            use_llm=use_llm,
            job_id=job_id,
        )
        if stream_ctx.get("has_stream"):
            await emit_stage_event(
                stream_ctx,
                "rag_compress.completed",
                query=q,
                hits=len(compressed_docs),
                input_hits=len(mmr_docs),
                output_hits=len(compressed_docs),
                input_chars=total_chars(mmr_docs),
                output_chars=total_chars(compressed_docs),
                max_context=max_context,
                use_llm=use_llm,
                heuristic_hits=heuristic_hits,
                llm_applied=llm_applied,
                took_ms=int((monotonic() - compress_started_at) * 1000),
            )
        logger.debug("[RAG] compressed_docs: %s", len(compressed_docs))
        state.compressed_docs = compressed_docs
        state.heuristic_hits = heuristic_hits
        state.llm_applied = llm_applied
        return state

    async def stage_join_context(self, inputs: RagState | Dict[str, Any]) -> RagState:
        state = self._ensure_state(inputs)
        docs = state.compressed_docs or state.mmr_docs or state.reranked_docs or state.docs or []
        compressed_docs = list(docs)
        if not compressed_docs:
            logger.warning("[RAG] No relevant documents found for query.")
            state.context = (
                "No relevant documents were found. Providing a general answer to the question."
            )
            state.citations = []
            return state

        context, citations = self.join_context(compressed_docs)
        state.context = context
        state.citations = citations
        return state

    async def stage_prompt(self, inputs: RagState | Dict[str, Any]) -> RagState:
        state = self._ensure_state(inputs)
        prompt_value = await self.prompt.ainvoke(
            {"question": state.question, "context": state.context or ""}
        )
        state.prompt = prompt_value
        return state

    async def stage_search_call_end(self, inputs: RagState | Dict[str, Any]) -> RagState:
        state = self._ensure_state(inputs)
        stream_ctx = state.stream_ctx or stream_context({"stream": state.stream})
        state.stream_ctx = stream_ctx
        hits = len(
            state.compressed_docs
            or state.mmr_docs
            or state.reranked_docs
            or state.docs
            or []
        )
        started_at = state.extra.get("search_call_started_at")
        took_ms = None
        if isinstance(started_at, (int, float)):
            took_ms = int((monotonic() - started_at) * 1000)
        if stream_ctx.get("has_stream"):
            await emit_search_event(
                stream_ctx,
                "rag_search_call.completed",
                query=state.question,
                hits=hits,
                took_ms=took_ms,
            )
        return state

    def build(self):
        """
        Create the final RAG chain (prompt).
        Injects context via a retriever step.
        """
        return (
            RunnableLambda(self.stage_search_call_start)
            | RunnableLambda(self.stage_retrieve)
            | RunnableLambda(self.stage_rerank)
            | RunnableLambda(self.stage_mmr)
            | RunnableLambda(self.stage_compress)
            | RunnableLambda(self.stage_join_context)
            | RunnableLambda(self.stage_prompt)
            | RunnableLambda(self.stage_search_call_end)
        )

def make_rag_chain(
    settings: RagConfig | None = None,
    pipeline: RagPipeline | None = None,
    embeddings: Embeddings | None = None,
):
    """
    Create a RAG chain from a RagPipeline instance.

    If an existing pipeline is not provided, embeddings must be given so that
    RagPipeline can be constructed correctly.
    """
    if pipeline is None:
        if embeddings is None:
            raise ValueError(
                "Embeddings must be provided when constructing a new RagPipeline: "
                "make_rag_chain(embeddings=...)"
            )
        pipe = RagPipeline(settings=settings, embeddings=embeddings)
    else:
        pipe = pipeline
    return pipe.build()
