import json
from logging import getLogger

import weaviate
from typing import Dict, Any, List, Optional, Sequence, TYPE_CHECKING, cast
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from chat_worker.application.rag.document import Document
from chat_worker.application.rag.helpers import kw_tokens, kw_hit, normalize_search_type
from chat_worker.application.rag.retrievers.base import RagContext, RetrieveResult
from chat_worker.application.rag.retrievers.weaviate_near_text import WeaviateNearTextRetriever
from chat_worker.settings import Settings, RagConfig, WeaviateSearchType
from chat_worker.application.rag.retrievers.weaviate_hybrid import WeaviateHybridRetriever

if TYPE_CHECKING:
    from langchain.retrievers.document_compressors import (
        BaseDocumentCompressor,
        BaseDocumentTransformer,
    )
else:  # pragma: no cover - only needed for static typing
    BaseDocumentTransformer = BaseDocumentCompressor = Any


logger = getLogger("RagPipeline")

#
# ---------------- Document helpers (shared across pipeline/retrievers) ----------------
def doc_stable_key(d: Any):
    """
    Return a stable, hashable key for a document or chunk.

    Preference order:
      1) Explicit IDs: doc_id, or (file_id, chunk_index)
      2) Metadata IDs: weaviate_id, id, uuid, chunk_id
      3) (title, chunk_index) as a soft key
      4) Fallback to object identity (id)
    Pure function; works with both custom and LangChain Documents.
    """
    # 1) Explicit IDs on our model
    if getattr(d, "doc_id", None):
        return d.doc_id
    if getattr(d, "file_id", None) and getattr(d, "chunk_index", None) is not None:
        return d.file_id, d.chunk_index

    # 2) Metadata-based IDs
    meta = d.metadata if isinstance(d.metadata, dict) else {}
    for k in ("weaviate_id", "id", "uuid", "chunk_id"):
        v = meta.get(k)
        if v:
            return v

    # 3) Soft key: title + chunk_index
    if getattr(d, "title", None) and getattr(d, "chunk_index", None) is not None:
        return d.title, d.chunk_index

    # 4) Absolute fallback
    return id(d)

def doc_score(d: Document) -> float:
    """
    Estimate a document's score for ranking.

    Priority:
      - Document.score (if present and numeric)
      - metadata["__orig_score"]
      - metadata["score"]
      - 1 - metadata["distance"] (distance to similarity)
      - -inf if unknown
    """
    # Prefer model-level score
    score = getattr(d, "score", None)
    if isinstance(score, (int, float, str)):
        try:
            return float(score)
        except Exception:
            pass

    meta = d.metadata if isinstance(d.metadata, dict) else {}
    if meta.get("__orig_score") is not None:
        try:
            return float(meta["__orig_score"])
        except Exception:
            return float("-inf")
    if meta.get("score") is not None:
        try:
            return float(meta["score"])
        except Exception:
            pass
    if meta.get("distance") is not None:
        try:
            return 1.0 - float(meta["distance"])
        except Exception:
            pass
    return float("-inf")

def doc_rank(d: Document) -> int:
    """
    Return original retrieval rank if available; higher value means worse rank.

    Falls back to a large number if rank is unavailable to preserve
    ordering among items with known ranks.
    """
    meta = d.metadata if isinstance(d.metadata, dict) else {}
    raw_rank = meta.get("__orig_rank")
    try:
        if isinstance(raw_rank, (int, float, str)):
            return int(raw_rank)
        return 10**9
    except Exception:
        return 10**9

class RagPipeline:
    """
    RAG pipeline using LangChain 1.x and Weaviate 1.x.

    Manages environment, settings, and retriever construction per request.
    Supports Weaviate Collections API (BM25/Hybrid) and LangChain VectorStore (similarity/MMR).
    Provides optional document compression and robust fallbacks (similarity → BM25 → MMR) with score preservation.

    Notes:
      - Hybrid search uses dynamic alpha and keyword guards to avoid filename-only bias.
      - Query normalization handles Korean–ASCII boundaries and tech term aliases.
      - Context packing enforces a strict budget while preserving ranking signals.
    """
    try:
        from langchain.retrievers.document_compressors import DocumentCompressorPipeline, \
            EmbeddingsFilter  # type: ignore
    except Exception:
        DocumentCompressorPipeline = None  # type: ignore
        EmbeddingsFilter = None  # type: ignore
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
            search_type: WeaviateSearchType = WeaviateSearchType.HYBRID,
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

        # Prompt
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.settings.rag_prompt),
                ("human", "질문: {question}\n\nContext:\n{context}\n\n답변:")
            ]
        )

    def compress_docs(self, docs: Sequence[Document], query: str):
        """
        Compress retrieved documents while preserving original scores and ranks.
        Uses embedding filter (if available), keyword guard, and context budget.
        Returns an ordered subset for prompt context.
        """
        # Normalize all incoming docs to our Document model
        try:
            docs = [Document.from_any(d) for d in docs]
        except Exception:
            docs = [d if isinstance(d, Document) else Document.from_langchain(d) for d in docs]

        # --- annotate original docs (compatible with custom Document & LangChain Document) ---
        for d in docs:
            md = d.metadata
            if not isinstance(md, dict):
                if isinstance(md, str):
                    try:
                        md = json.loads(md)
                    except Exception:
                        md = {}
                else:
                    md = {}
            d.metadata = md

        DC, EF = self.DocumentCompressorPipeline, self.EmbeddingsFilter
        filtered = None
        used_thresh = None

        # --- build keyword guard from query tokens ---
        toks = kw_tokens(query)
        must_keep: list = []
        try:
            # keep at most 2 strong keyword hits from original order
            for d in docs:
                if len(must_keep) >= 3:  # 2 -> 3
                    break
                if kw_hit(toks, d):
                    must_keep.append(d)
        except Exception:
            must_keep = []

        # --- compressor with adaptive threshold ---
        if DC and EF:
            for th in (0.20, 0.10, 0.0):
                try:
                    compressor = DC(
                        transformers=cast(
                            "list[BaseDocumentTransformer | BaseDocumentCompressor]",
                            [
                                EF(
                                    embeddings=self.embeddings,
                                    similarity_threshold=th,
                                )
                            ],
                        )
                    )
                    out = compressor.compress_documents(cast("Sequence[Any]", docs), query)
                    # ensure at least some docs remain; if not, relax further
                    if out and len(out) >= 2:
                        filtered = out
                        used_thresh = th
                        break
                    # if nothing/too few, try lower threshold
                except Exception as e:
                    logger.warning(f"[RAG] compressor failed (th={th}): {e}")
                    filtered = None
                    used_thresh = th
                    break
        # Fallback when no compressor or it failed entirely
        if filtered is None:
            filtered = list(docs)
            used_thresh = -1

        # Always keep the first retrieved doc as an anchor.
        anchor = docs[0] if docs else None
        keep_set = set()
        kept: list = []

        # add anchor first
        if anchor:
            k = doc_stable_key(anchor)
            keep_set.add(k)
            kept.append(anchor)

        # add keyword-guard docs
        for d in must_keep:
            k = doc_stable_key(d)
            if k not in keep_set:
                keep_set.add(k)
                kept.append(d)

        # add filtered results in original order
        for d in filtered:
            k = doc_stable_key(d)
            if k not in keep_set:
                keep_set.add(k)
                kept.append(d)

        # Snippet extraction disabled: keep full chunk content for maximum recall.
        # Keep original `page_content` for all kept docs; no density filtering.
        # Maximizes recall at the cost of longer context.
        kept = list(kept)

        # Restore stable order by original score, then rank.
        kept = sorted(kept, key=lambda d: (-doc_score(d), doc_rank(d)))

        # --- trim to context budget ---
        out, total = [], 0
        max_context = self.max_context
        for d in kept:
            ln = len(d.page_content or "")
            if max_context is not None and total + ln > max_context:
                continue
            out.append(d)
            total += ln

        # Guarantee at least a small set
        if not out:
            out = kept[: min(len(kept), 8)]  # 6 -> 8

        try:
            logger.info(
                f"[RAG][compress] in={len(docs)} used_th={used_thresh} kw_keep={len(must_keep)} out={len(out)} dens='full'")
        except Exception:
            pass

        return out

    def join_context(self, docs: List[Document]) -> str:
        """
        Pack documents into a single context string with file and section headers.
        Respects the context budget and logs skipped chunks if the budget is exceeded.
        """
        try:
            docs = [Document.from_any(d) for d in docs]
        except Exception:
            docs = [d if isinstance(d, Document) else Document.from_langchain(d) for d in docs]

        buf, total = [], 0
        budget = self.max_context
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
                logger.info("[RAG][ctx-pack] want=%s left=%s file=%s chunk=%s",
                            ln, left, title,
                            (getattr(d, "chunk_index", None) or (d.metadata.get("chunk_index") if isinstance(d.metadata, dict) else None)))
            except Exception:
                pass

            if budget is not None and total + ln > budget:
                try:
                    left = (budget - total) if budget is not None else float("inf")
                    logger.info("[RAG][ctx-pack] SKIP due to budget: file=%s chunk=%s need=%s left=%s",
                                title,
                                (getattr(d, "chunk_index", None) or (d.metadata.get("chunk_index") if isinstance(d.metadata, dict) else None)),
                                ln, left)
                except Exception:
                    pass
                continue

            buf.append(f"[{title}]{' > ' + section if section else ''}\n{txt}\n")
            total += ln

        return "\n---\n".join(buf)

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
        logger.info(f"[RAG] search_type: {st.value}")
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
            filters=filters,
            settings=self.settings,
        )
        if st == WeaviateSearchType.NEAR_TEXT:
            return WeaviateNearTextRetriever(ctx)
        else:
            return WeaviateHybridRetriever(ctx)

    def build(self):
        """
        Create the final RAG chain (prompt).
        Injects context via a retriever step.
        """
        def _with_context(inputs: Dict[str, Any]):
            """
            Retrieve and compress context for the input question.
            Return prompt variables for downstream processing.
            """
            rag_cfg = inputs.get("rag", {}) or {}
            retriever = self.build_retriever(
                top_k=rag_cfg.get("topK"),
                mmq=rag_cfg.get("mmq"),
                filters=rag_cfg.get("filters"),
                search_type=rag_cfg.get("searchType"),
                alpha=rag_cfg.get("alpha"),
            )
            q = inputs["question"]
            # Build a fresh retriever for this request and run the initial search.
            docs_seq: Sequence[Document]
            try:
                try:
                    logger.info(
                        f"[RAG] cfg topK={rag_cfg.get('topK')} mmq={rag_cfg.get('mmq')} filters={rag_cfg.get('filters')}")
                except Exception:
                    pass
                result = retriever.invoke(q)
                docs_seq = self._extract_docs(result)
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
                            mmq=rag_cfg.get("mmq"),
                            filters=rag_cfg.get("filters"),
                            text_key=tk,
                        )
                        fallback_result = retriever2.invoke(q)
                        docs_seq = self._extract_docs(fallback_result)
                        # Success: remember the working text_key for subsequent calls
                        self.text_key = tk
                        break
                    except KeyError as ee:
                        last_err = ee
                        continue
                else:
                    raise last_err
            docs = list(docs_seq)
            compressed_docs = self.compress_docs(docs, q)
            logger.info("[RAG] compressed_docs: %s", len(compressed_docs))
            if not compressed_docs:
                logger.warning("[RAG] No relevant documents found for query.")
                return {
                    "question": q,
                    "context": "No relevant documents were found. Providing a general answer to the question.",
                }

            context = self.join_context(compressed_docs)
            return {"question": q, "context": context}

        def _log_prompt_value(pv):
            """
            Pretty-print the final prompt value for debugging (messages and roles).
            """
            try:
                msgs = pv.to_messages()
                logger.info("[PROMPT] -----")
                for m in msgs:
                    role = getattr(m, "type", None) or getattr(m, "role", "")
                    content = getattr(m, "content", "")
                    logger.info(f"[{role}] {content}")
                logger.info("-----")
            except Exception:
                try:
                    logger.info("[PROMPT_STR] %s", pv.to_string())
                except Exception:
                    logger.info("[PROMPT_RAW] %s", pv)
            return pv

        return (
                RunnableLambda(_with_context)
                | self.prompt
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
