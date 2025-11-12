from typing import Any, Mapping, Final, cast

from chat_worker.application.rag.retrievers.base import BaseRetriever, RagContext
from chat_worker.application.rag.retrievers.weaviate_hybrid import WeaviateHybridRetriever
from chat_worker.application.rag.retrievers.weaviate_near_text import WeaviateNearTextRetriever

# Stable registry of available retrievers (read-only by type)
REGISTRY: Final[Mapping[str, type[BaseRetriever]]] = cast(
    dict[str, type[BaseRetriever]],
    cast(object, {
        "weaviate_hybrid": WeaviateHybridRetriever,
        "weaviate_near_text": WeaviateNearTextRetriever
    })
)

def create_retriever(
    name: str,
    *,
    client: Any,
    collection: str,
    embeddings: Any,
    settings: Any | None = None,
    text_key: str = "text",
    alpha: float = 0.5,
    default_top_k: int = 6,
) -> BaseRetriever:
    """
    Factory for retrievers.

    Returns:
        retriever: An instance with its internal RagContext injected.
    """
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown retriever: {name}")

    ctx = RagContext(
        client=client,
        collection=collection,
        embeddings=embeddings,
        settings=settings,
        text_key=text_key,
        alpha=alpha,
        default_top_k=default_top_k,
    )
    retriever = cls(ctx)
    return retriever