from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, TypedDict, Sequence

# -----------------------------------------------------------------------------
# Core domain types for RAG retrieval
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class RagContext:
    """
    Immutable runtime dependencies for retrievers.

    Fields:
    - client: backend client/connection (e.g., Weaviate client)
    - collection: name of the collection / class to query
    - embeddings: embedder/encoder used for vector queries
    - text_key: property key for fulltext/BM25 queries (default: 'text')
    - alpha: hybrid mixing parameter when supported (0.0~1.0)
    - default_top_k: fallback value when caller doesn't provide top_k
    - filters: optional backend filter object (mapping), applied by retrievers
    - settings: optional settings object (free-form)
    """
    client: Any
    collection: str
    embeddings: Any
    text_key: str = "text"
    alpha: float = 0.5
    default_top_k: int = 5
    filters: Mapping[str, Any] | None = None
    settings: Any | None = None


@dataclass
class RagDocument:
    """
    Normalized document shape shared by all retrievers.
    """
    title: str
    content: str
    file_id: str | None = None
    doc_id: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Pretty debug representation (keeps logs readable)
    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Document(title={self.title!r}, doc_id={self.doc_id!r}, "
            f"file_id={self.file_id!r}, len={len(self.content)}, "
            f"score={self.score!r}, page={self.page!r}, chunk_index={self.chunk_index!r})"
        )


class RetrieveResult(TypedDict, total=False):
    """
    Standard return type for retrievers.

    Required keys used across the codebase:
    - docs: ordered list of RagDocument (highest score first)
    - query: the original user query string
    - top_k: the effective K used for this retrieval

    Optional keys (backend/impl specific):
    - filters: effective filter object (mapping) or None
    - raw: backend-specific payload for debugging/telemetry
    """
    docs: Sequence[RagDocument]
    query: str
    top_k: int
    filters: Mapping[str, Any] | None
    raw: Any


# -----------------------------------------------------------------------------
# Base interface for retrievers
# -----------------------------------------------------------------------------

class BaseRetriever(ABC):
    """
    Retriever base class (constructor-injected context).

    Implementations should NOT perform backend connections in __init__.
    They receive a pre-built RagContext and use it during `invoke()` calls.

    Contract:
    - Pass a RagContext to the constructor and store on `self.ctx`.
    - `invoke()` is async and MUST return a `RetrieveResult` with a normalized
      list of `RagDocument` in the `docs` field.
    - Respect `top_k` if provided; otherwise fall back to `self.ctx.default_top_k`.
    - Apply `filters` when the backend supports it.
    """

    name: str = "base"

    def __init__(self, ctx: RagContext):
        # standard, read‑only runtime dependencies
        self.ctx = ctx

    @abstractmethod
    async def invoke(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> RetrieveResult:
        """
        Execute a retrieval for `query` using dependencies in `self.ctx`.

        Implementations should:
        1) respect `top_k` if provided, else fall back to `self.ctx.default_top_k`.
        2) apply `filters` when supported by the backend.
        3) return a RetrieveResult with a normalized `docs` list of RagDocument.
        """
        raise NotImplementedError


__all__ = ["RagContext", "RagDocument", "RetrieveResult", "BaseRetriever"]