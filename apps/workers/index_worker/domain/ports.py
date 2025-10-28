from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol, runtime_checkable, Sequence, Optional, Dict, Union, Any
from .entities import Chunk

@runtime_checkable
class VectorRepository(Protocol):
    @abstractmethod
    async def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        """
        Insert or update multiple document chunks and their embedding vectors in the vector store.
        Each chunk corresponds to a text segment with its associated vector representation.
        """
        ...

    @abstractmethod
    async def delete_by_user_file(self, user_id: str, file_id: str) -> int:
        """
        Delete all stored vectors for a specific (user_id, file_id) pair from the vector store.
        Returns the number of deleted objects for observability and metrics tracking.
        """
        ...

    async def close(self):
        """
        Close and release any resources or connections held by the vector store client.
        Typically called during graceful shutdown.
        """
        pass


@runtime_checkable
class ObjectStorage(Protocol):
    async def get_document_text(self, obj_key: str) -> str:
        """
        Fetch the raw document text from object storage using the given object key.
        Returns the full textual contents as a UTF-8 string.
        """
        ...

@runtime_checkable
class Embedder(Protocol):
    async def embed_batch(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """
        Compute embedding vectors for a batch of input texts.
        The order and length of the returned vectors must match the input sequence 1:1.
        """
        ...

@runtime_checkable
class EventPublisher(Protocol):
    async def publish(self, topic: str, payload: dict) -> None:
        """
        Publish an event payload to the specified topic on the underlying transport (e.g., Kafka).
        Implementations should be fire-and-forget and handle transport-specific concerns internally.
        """
        ...


class MetadataRepo(ABC):
    """
    Abstract Port for persisting and retrieving file metadata.
    Implemented by infrastructure layer (e.g., Postgres adapter).
    """

    @abstractmethod
    async def update_index_status(
            self,
            file_id: str,
            *,
            status: str,
            chunk_count: Optional[int] = None,
            embedding_model: Optional[str] = None,
            indexed_at: Optional[datetime] = None,
            vectorized_at: Optional[datetime] = None,
            meta_path: Optional[list[str]] = None,
            meta_value: Optional[Any] = None,
            meta: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> None:
        """
        Update metadata fields for a given file after indexing/vectorization.
        Supports either meta_path+meta_value (jsonb_set) or meta (shallow merge).
        """
        ...

    @abstractmethod
    async def get_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve metadata for a given file_id.
        """
        ...

    @abstractmethod
    async def mark_failed(self, file_id: str, reason: str) -> None:
        """
        Mark the file as failed (status='failed', meta.reason=reason)
        """
        ...

    @abstractmethod
    async def mark_deleted(self, file_id: str, deleted_count: Optional[int] = None, reason: Optional[str] = None) -> None:
        """
        Mark the file as deleted (status='deleted').
        Optionally persist the number of deleted vectors and a free-form reason for auditability.
        """
        ...
