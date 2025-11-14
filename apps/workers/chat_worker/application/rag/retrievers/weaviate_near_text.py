from logging import getLogger
from typing import Mapping, Any

import weaviate.classes as wvc

from chat_worker.application.rag.document import items_to_docs
from chat_worker.application.rag.helpers import log_items, resolve_context
from chat_worker.application.rag.retrievers.base import RagContext, RetrieveResult, BaseRetriever

logger = getLogger("WeaviateNearTextRetriever")

class WeaviateNearTextRetriever(BaseRetriever):
    """Retriever using Weaviate near_text with server-side vectorization."""
    name = "weaviate_near_text"

    def __init__(self, ctx: RagContext):
        super().__init__(ctx)
        self._ctx = ctx

    def invoke(
            self,
            query: str,
            *,
            top_k: int | None = None,
            filters: Mapping[str, Any] | None = None,
            **kwargs: Any,
    ) -> RetrieveResult:
        logger.info(f"[invoke] query={query} top_k={top_k} filters={filters}")
        ctx = getattr(self, "_ctx", None)
        if ctx is None:
            raise ValueError("RagContext is not set. Initialize WeaviateNearTextRetriever with ctx=RagContext.")

        # Dependencies from context
        client, collection_name, text_key, k, nf = resolve_context(ctx, top_k, filters)

        if client is None or not hasattr(client, "collections"):
            raise ValueError("Weaviate >=1.0 Collections API required for near_text")

        coll = client.collections.use(collection_name)

        try:
            res = coll.query.near_text(
                query=query,
                distance=0.7,
                limit=k,
                filters=nf,
                return_metadata=wvc.query.MetadataQuery(score=True, distance=True),
                return_properties=[text_key, "filename", "page", "chunk_index", "file_id", "chunk_id"],
            )
        except Exception as e:
            logger.error(f"query error: {e}")
            return RetrieveResult(docs=[], query=query, top_k=k, filters=dict(filters) if filters else None)

        items = list(getattr(res, "objects", None) or [])
        log_items(items, logger)

        docs = items_to_docs(items, text_key)
        return RetrieveResult(docs=docs, query=query, top_k=k, filters=dict(filters) if filters else None)