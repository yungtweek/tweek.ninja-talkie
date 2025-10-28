from __future__ import annotations

import time
import logging
from typing import TypedDict, Optional, Literal
from datetime import datetime, UTC

from index_worker.application.extract_text import clean_text, extract_text  # expects (raw_bytes, filename)
from index_worker.application.chunking import chunk_text
from index_worker.domain.ports import Embedder, MetadataRepo, VectorRepository

logger = logging.getLogger(__name__)

# --- Result type ------------------------------------------------------------
class IndexResult(TypedDict, total=False):
    ok: bool
    chunks: int
    duration_ms: int
    error: str | None
    file_id: str
    filename: str
    user_id: str
    mode: Literal["word", "char", "token"]
    chunk_size: int
    overlap: int


# --- Orchestrator -----------------------------------------------------------
async def index_document(
    *,
    user_id: str,
    file_id: str,
    filename: str,
    raw_bytes: bytes,
    embedder: Embedder,
    vector_repo: VectorRepository,
    metadata_repo: Optional[MetadataRepo] = None,
    embedding_model: Optional[str] = None,
    chunk_mode: Literal["word", "char", "token"] = "token",
    chunk_size: int = 500,
    overlap: int = 50,
) -> IndexResult:
    """
    End-to-end indexing pipeline (pure application logic):
      bytes -> text -> cleaned -> chunks -> embeddings -> vector upsert

    Dependencies (embedder, vector_repo) are injected for testability & hexagonal design.
    """
    t0 = time.time()

    # Basic guards
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise TypeError("raw_bytes must be bytes")
    if not filename:
        raise ValueError("filename is required for type inference")

    try:
        # 1) Extract
        text = extract_text(raw_bytes, filename)
        if not text or not text.strip():
            return _done(False, t0, user_id, file_id, filename, chunk_mode, chunk_size, overlap, error="No extractable text")

        # 2) Clean
        text = clean_text(text)
        if not text:
            return _done(False, t0, user_id, file_id, filename, chunk_mode, chunk_size, overlap, error="Empty after cleaning")

        # 3) Chunk
        chunks = chunk_text(
            text=text,
            file_id=file_id,
            user_id=user_id,
            filename=filename,
            chunk_size=chunk_size,
            overlap=overlap,
            mode=chunk_mode,
        )
        if not chunks:
            return _done(False, t0, user_id, file_id, filename, chunk_mode, chunk_size, overlap, error="No chunks produced")

        # 3.5) Update metadata: chunk count & indexed_at
        if metadata_repo:
            try:
                await metadata_repo.update_index_status(
                    file_id,
                    status="indexed",
                    chunk_count=len(chunks),
                    indexed_at=datetime.now(UTC),
                    meta_path=["status"],
                    meta_value="indexed",
                )
            except Exception as me:
                logger.warning("metadata update (indexed) failed: %s", me)

        # 4) Embed (batch)
        vectors = await embedder.embed_batch([c.text.text for c in chunks])
        if not vectors or len(vectors) != len(chunks):
            return _done(False, t0, user_id, file_id, filename, chunk_mode, chunk_size, overlap, error="Embedding size mismatch")

        # 5) Upsert to vector store (idempotent by chunk_id)
        await vector_repo.upsert(chunks, vectors)

        # 5.5) Update metadata: embedding model & vectorized_at
        if metadata_repo:
            try:
                await metadata_repo.update_index_status(
                    file_id,
                    status="vectorized",
                    embedding_model=(embedding_model or "unknown"),
                    vectorized_at=datetime.now(UTC),
                    meta_path=["status"],
                    meta_value="vectorized",
                )
                logger.info("metadata updated")
            except Exception as me:
                logger.warning("metadata update (vectorized) failed: %s", me)

        return _done(True, t0, user_id, file_id, filename, chunk_mode, chunk_size, overlap, chunks=len(chunks))

    except Exception as e:
        logger.exception("index_document failed: %s", e)
        # try:
        if metadata_repo:
            await metadata_repo.mark_failed(file_id, str(e))
        # except Exception:
        #     pass
        return _done(False, t0, user_id, file_id, filename, chunk_mode, chunk_size, overlap, error=str(e))


# --- helpers ----------------------------------------------------------------

def _done(
    ok: bool,
    t0: float,
    user_id: str,
    file_id: str,
    filename: str,
    mode: Literal["word", "char", "token"],
    chunk_size: int,
    overlap: int,
    *,
    chunks: int = 0,
    error: Optional[str] = None,
) -> IndexResult:
    return {
        "ok": ok,
        "chunks": chunks,
        "duration_ms": int((time.time() - t0) * 1000),
        "error": error or "",
        "file_id": file_id,
        "filename": filename,
        "user_id": user_id,
        "mode": mode,
        "chunk_size": chunk_size,
        "overlap": overlap,
    }