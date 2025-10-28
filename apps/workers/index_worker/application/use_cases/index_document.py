from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal

from index_worker.application.index_document import index_document, IndexResult
from index_worker.domain.ports import VectorRepository
from index_worker.domain.ports import MetadataRepo
from index_worker.domain.ports import Embedder


@dataclass(frozen=True)
class IndexDocumentCommand:
    user_id: str
    file_id: str
    filename: str
    raw_bytes: bytes
    # Optional params
    embedding_model: Optional[str] = None
    chunk_mode: Literal["word", "char", "token"] = "token"
    chunk_size: int = 500
    overlap: int = 50


class IndexDocumentUseCase:
    """
    Thin application layer:
    - Injects infrastructure dependencies (Embedder / VectorRepo / MetadataRepo)
    - Delegates the command input to the orchestrator (index_document)
    - Returns the original IndexResult object without transformation
    """
    def __init__(
            self,
            *,
            embedder: Embedder,
            vector_repo: VectorRepository,
            metadata_repo: Optional[MetadataRepo] = None,
            default_embedding_model: Optional[str] = None,
            default_chunk_mode: Literal["word", "char", "token"] = "token",
            default_chunk_size: int = 500,
            default_overlap: int = 50,
    ) -> None:
        self.embedder = embedder
        self.vector_repo = vector_repo
        self.metadata_repo = metadata_repo
        self.default_embedding_model = default_embedding_model
        self.default_chunk_mode = default_chunk_mode
        self.default_chunk_size = default_chunk_size
        self.default_overlap = default_overlap

    async def execute(self, cmd: IndexDocumentCommand) -> IndexResult:
        return await index_document(
            user_id=cmd.user_id,
            file_id=cmd.file_id,
            filename=cmd.filename,
            raw_bytes=cmd.raw_bytes,
            embedder=self.embedder,
            vector_repo=self.vector_repo,
            metadata_repo=self.metadata_repo,
            embedding_model=cmd.embedding_model or self.default_embedding_model,
            chunk_mode=cmd.chunk_mode or self.default_chunk_mode,
            chunk_size=cmd.chunk_size or self.default_chunk_size,
            overlap=cmd.overlap or self.default_overlap,
        )