from logging import getLogger

import weaviate
from typing import Dict, Any, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_weaviate import WeaviateVectorStore
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from chat_worker.settings import Settings, RagConfig
logger = getLogger("RagPipeline")


# ---------------------------------------------------------------------------

class RagPipeline:
    """
    Class-based RAG pipeline:
     - Encapsulates env/config
     - Manages Weaviate client, embeddings
     - Provides retriever construction, compression, join_context
     - Exposes .chain(llm) -> Runnable for worker
    """
    # Guarded imports for LC 1.x vs older variants
    try:
        from langchain.retrievers.document_compressors import DocumentCompressorPipeline, EmbeddingsFilter  # type: ignore
    except Exception:
        DocumentCompressorPipeline = None  # type: ignore
        EmbeddingsFilter = None  # type: ignore
    try:
        from langchain.retrievers.multi_query import MultiQueryRetriever  # type: ignore
    except Exception:
        MultiQueryRetriever = None  # type: ignore

    def __init__(
        self,
        *,
        settings: RagConfig | None = None,
        weaviate_url: str | None = None,
        weaviate_api_key: str | None = None,
        collection: str | None = None,
        text_key: str | None = None,
        embedding_model: str | None = None,
        client: Optional[weaviate.WeaviateClient] = None,
        embeddings: Optional[Embeddings] = None,
        llm: Optional[BaseLanguageModel] = None,
        default_top_k: int | None = None,
        default_mmq: int | None = None,
        max_context: int | None = None,
        search_type: str | None = None,
    ):
        self.settings = settings or Settings().RAG
        # allow per-instance override via kwargs (take kwargs over settings)
        self.weaviate_url = weaviate_url or self.settings.weaviate_url
        self.weaviate_api_key = weaviate_api_key or self.settings.weaviate_api_key
        self.collection = collection or self.settings.collection
        self.text_key = text_key or self.settings.text_key
        self.embedding_model = embedding_model or self.settings.embedding_model
        self.default_top_k = int(default_top_k or self.settings.top_k)
        self.default_mmq = int(default_mmq or self.settings.mmq)
        self.max_context = int(max_context or self.settings.max_context)
        self.search_type = (search_type or self.settings.search_type).lower()

        self.client = client
        self.embeddings = embeddings
        self.llm = llm  # may be None; chain() will validate

        # Prompt
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.settings.rag_prompt),
                ("human", "질문: {question}\n\nContext:\n{context}\n\n답변:")
            ]
        )

    # ---------------- Filters / Compression / Utils ----------------
    @staticmethod
    def normalize_filters(filters: Dict[str, Any] | None):
        if not filters:
            return None
        ops = []
        for k, v in filters.items():
            if isinstance(v, list):
                sub = []
                for item in v:
                    if isinstance(item, bool):
                        sub.append({"path": [k], "operator": "Equal", "valueBoolean": item})
                    elif isinstance(item, (int, float)):
                        sub.append({"path": [k], "operator": "Equal", "valueNumber": item})
                    else:
                        sub.append({
                            "path": [k],
                            "operator": "TextContains",  # ✅ 부분 일치 + 대소문자 무시
                            "valueText": str(item).lower(),
                        })
                ops.append({"operator": "Or", "operands": sub})
            elif isinstance(v, bool):
                ops.append({"path": [k], "operator": "Equal", "valueBoolean": v})
            elif isinstance(v, (int, float)):
                ops.append({"path": [k], "operator": "Equal", "valueNumber": v})
            else:
                ops.append({
                    "path": [k],
                    "operator": "TextContains",  # ✅ 문자열 일치 대신 contains
                    "valueText": str(v).lower(),
                })
        return {"operator": "And", "operands": ops} if len(ops) > 1 else (ops[0] if ops else None)

    def compress_docs(self, docs: List, query: str):
        """Use LC compressor if available; otherwise trim by char budget."""
        DC, EF = self.DocumentCompressorPipeline, self.EmbeddingsFilter
        if DC and EF:
            try:
                compressor = DC(transformers=[EF(embeddings=self.embeddings, similarity_threshold=0.35)])
                return compressor.compress_documents(docs, query=query)
            except Exception:
                pass
        # Fallback: simple budget trim
        kept, total = [], 0
        for d in docs:
            ln = len(d.page_content or "")
            if total + ln > self.max_context:
                continue
            kept.append(d)
            total += ln
        return kept or docs[: min(len(docs), 6)]

    def join_context(self, docs: List) -> str:
        try:
            print("[RAG] top docs meta:", [
                (getattr(d, "id", None), (d.metadata or {})) for d in docs[:5]
            ])
        except Exception:
            pass
        buf, total = [], 0
        for d in docs:
            txt = d.page_content
            if total + len(txt) > self.max_context:
                break
            meta = d.metadata or {}
            title = (
                    meta.get("title")
                    or meta.get("filename")    # ✅ 우리 스키마
                    or meta.get("file_name")   # 혹시 다른 파이프라인
                    or meta.get("source")      # 종종 쓰는 키
                    or "Untitled"
            )
            section = meta.get("section") or ""
            buf.append(f"[{title}]{' > ' + section if section else ''}\n{txt}\n")
            total += len(txt)
        return "\n---\n".join(buf)

    # ---------------- Retriever / Chain ----------------
    def build_retriever(self, *, top_k: int | None = None, mmq: int | None = None, filters: Dict[str, Any] | None = None, llm: Optional[BaseLanguageModel] = None, text_key: Optional[str] = None, search_type: Optional[str] = None):
        if self.client is None:
            raise ValueError("Weaviate client must be injected: RagPipeline(client=...)")
        if self.embeddings is None:
            raise ValueError("Embeddings must be injected: RagPipeline(embeddings=...)")

        filters = self.normalize_filters(filters)
        # Compute effective search type and search kwargs
        st = (search_type or self.search_type or "similarity").lower()
        # LangChain VectorStoreRetriever for Weaviate does not accept 'hybrid' here.
        # Supported: ('similarity', 'similarity_score_threshold', 'mmr')
        if st == "hybrid":
            try:
                logger.warning("[RAG] 'hybrid' search_type not supported by VectorStoreRetriever; falling back to 'mmr'")
            except Exception:
                pass
            st = "mmr"
        kwargs: Dict[str, Any] = {"k": int(top_k or self.default_top_k)}
        if filters:
            kwargs["filters"] = filters
        # Vector store backed retriever (Weaviate v4 client)
        vs = WeaviateVectorStore(
            client=self.client,
            index_name=self.collection,
            text_key=(text_key or self.text_key),
            embedding=self.embeddings,
            attributes=["filename", "page", "chunk_index", "user_id", "file_id", "chunk_id"],  # ✅ 추가
        )
        retriever = vs.as_retriever(
            search_type=st if st in ("similarity", "hybrid") else "similarity",
            search_kwargs=kwargs,
        )
        # Multi-query expansion if available
        if (mmq or self.default_mmq) and self.MultiQueryRetriever is not None:
            try:
                count = int(mmq or self.default_mmq)
                custom_prompt = None
                # If you want a different number than the library default (often 3),
                # provide a custom prompt that asks for `count` queries.
                if count and count != 3:
                    custom_prompt = PromptTemplate.from_template(
                        "You are a helpful assistant tasked with reformulating a user question into {count} diverse search queries for retrieval.\n"
                        "Original question:\n{question}\n\n"
                        "Return exactly {count} queries, one per line, without numbering."
                    ).partial(count=str(count))
                effective_llm = llm or self.llm
                if effective_llm is None:
                    # If no LLM is injected/provided, skip multi-query to avoid creating a new instance implicitly
                    return retriever
                retriever = self.MultiQueryRetriever.from_llm(
                    retriever=retriever,
                    llm=effective_llm,
                    include_original=True,
                    **({"prompt": custom_prompt} if custom_prompt else {})
                )
            except Exception:
                pass
        return retriever

    def build(self, llm: Optional[BaseLanguageModel] = None):
        used_llm = llm or self.llm
        if used_llm is None:
            raise ValueError("LLM must be provided: inject via RagPipeline(llm=...) or pass to chain(llm=...).")

        def _with_context(inputs: Dict[str, Any]):
            rag_cfg = inputs.get("rag", {}) or {}
            retriever = self.build_retriever(
                top_k=rag_cfg.get("topK"),
                mmq=rag_cfg.get("mmq"),
                filters=rag_cfg.get("filters"),
                llm=used_llm,
            )
            q = inputs["question"]
            try:
                try:
                    logger.info(f"[RAG] cfg topK={rag_cfg.get('topK')} mmq={rag_cfg.get('mmq')} filters={rag_cfg.get('filters')}")
                except Exception:
                    pass
                docs = retriever.invoke(q)
                # Fallbacks: if nothing returned, retry without filters, then hybrid
                if not docs:
                    try:
                        logger.info("[RAG] no docs with current filters; retrying without filters")
                    except Exception:
                        pass
                    retriever_nf = self.build_retriever(
                        top_k=rag_cfg.get("topK"),
                        mmq=rag_cfg.get("mmq"),
                        filters=None,
                        llm=used_llm,
                    )
                    docs = retriever_nf.invoke(q)
                if not docs and (self.search_type or "similarity") != "hybrid":
                    try:
                        try:
                            logger.info("[RAG] still no docs; retrying with mmr search_type (hybrid not supported)")
                        except Exception:
                            pass
                        retriever_hy = self.build_retriever(
                            top_k=rag_cfg.get("topK"),
                            mmq=rag_cfg.get("mmq"),
                            filters=None,
                            llm=used_llm,
                            search_type="mmr",
                        )
                        docs = retriever_hy.invoke(q)
                    except Exception as e:
                        try:
                            logger.warning(f"[RAG] hybrid retry failed: {getattr(e, 'message', str(e))}")
                        except Exception:
                            pass
                        # Keep docs as empty so the downstream 'no docs' fallback triggers
                        docs = []
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
                            llm=used_llm,
                            text_key=tk,
                        )
                        docs = retriever2.invoke(q)
                        # Success: remember the working text_key for subsequent calls
                        self.text_key = tk
                        break
                    except KeyError as ee:
                        last_err = ee
                        continue
                else:
                    raise last_err
            if not docs:
                logger.warning("[RAG] No relevant documents found for query.")
                return {
                    "question": q,
                    "context": "⚠️ 관련 정보를 찾지 못했습니다. 질문에 대한 일반적인 답변을 제공합니다.",
                }

            context = self.join_context(self.compress_docs(docs, q))
            return {"question": q, "context": context}

        return (
            RunnableLambda(_with_context)
            | self.prompt
            | used_llm.with_config(tags=["final_answer"])
        )

def make_rag_chain(llm: Optional[BaseLanguageModel] = None, settings: RagConfig | None = None, pipeline: RagPipeline | None = None):
    pipe = pipeline or RagPipeline(settings=settings, llm=llm)
    return pipe.build()