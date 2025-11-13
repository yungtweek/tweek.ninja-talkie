from __future__ import annotations

import time
import logging
from typing import TypedDict, Optional, Literal, Awaitable, Callable, Any
from datetime import datetime, UTC

from index_worker.application.chunking.base import ChunkingInput, ChunkMode
from index_worker.application.chunking.factory import build_chunker
from index_worker.application.extract_text import clean_text, extract_text
from index_worker.domain.ports import Embedder, MetadataRepo, VectorRepository

logger = logging.getLogger(__name__)

async def _safe_emit(
    emit_event: Optional[Callable[[dict[str, Any]], Awaitable[None]]],
    type_name: str,
    payload: dict[str, Any],
    *,
    v: int = 1,
    ts: Optional[int] = None,
    correlation_id: Optional[str] = None,
    source: Optional[Literal["gateway", "worker", "api"]] = None,
) -> None:
    if emit_event is None:
        return
    try:
        event: dict[str, Any] = {
            "v": v,
            "ts": ts if ts is not None else int(time.time() * 1000),
            "type": type_name,
            "payload": payload,
        }
        if correlation_id is not None:
            event["correlationId"] = correlation_id
        if source is not None:
            event["from"] = source
        await emit_event(event)
    except Exception as e:
        logger.warning("event emit failed: %s", e)

# --- Result type ------------------------------------------------------------
class IndexResult(TypedDict, total=False):
    ok: bool
    chunks: int
    duration_ms: int
    error: str | None
    file_id: str
    filename: str
    user_id: str
    mode: ChunkMode
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
    emit_event: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    embedding_model: Optional[str] = None,
    chunk_mode: ChunkMode,
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

    effective_mode: ChunkMode = chunk_mode

    try:
        filename_lower = filename.lower()
        if filename_lower.endswith(".md"):
            effective_mode = "markdown"
        # 1) Extract
        text = extract_text(raw_bytes, filename)
        if not text or not text.strip():
            return _done(False, t0, user_id, file_id, filename, effective_mode, chunk_size, overlap, error="No extractable text")

        # 2) Clean
        text = clean_text(text)
        if not text:
            return _done(False, t0, user_id, file_id, filename, effective_mode, chunk_size, overlap, error="Empty after cleaning")

        # 3) Chunk
        chunker = build_chunker(mode=effective_mode)

        chunks = chunker.chunk(
            ChunkingInput(
                text=text,
                file_id=file_id,
                user_id=user_id,
                filename=filename,
            ),
            chunk_size=chunk_size,
            overlap=overlap,
        )

        if not chunks:
            return _done(False, t0, user_id, file_id, filename, effective_mode, chunk_size, overlap, error="No chunks produced")

        # 3.5) Update metadata: chunk count & indexed_at
        if metadata_repo:
            try:
                await metadata_repo.save_chunks(chunks)
                await metadata_repo.update_index_status(
                    file_id,
                    status="indexed",
                    chunk_count=len(chunks),
                    indexed_at=datetime.now(UTC),
                    meta={"status": "indexed",
                          "chunk_mode": effective_mode},
                )
                await _safe_emit(emit_event, "file.status.changed", {
                    "id": file_id,
                    "prev": "ready",
                    "next": "indexed"
                })
            except Exception as me:
                logger.warning("metadata update (indexed) failed: %s", me)

        # 4) Embed (batch)
        # await _safe_emit(emit_event, {
        #     "type": "status",
        #     "fileId": file_id,
        #     "userId": user_id,
        #     "status": "vectorizing",  # transitional state (optional)
        #     "ts": int(time.time() * 1000),
        # })
        vectors = await embedder.embed_batch([c.text.text for c in chunks])
        if not vectors or len(vectors) != len(chunks):
            return _done(False, t0, user_id, file_id, filename, effective_mode, chunk_size, overlap, error="Embedding size mismatch")

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
                await _safe_emit(emit_event, "file.status.changed", {
                    "id": file_id,
                    "prev": "indexed",
                    "next": "vectorized"
                })
                logger.info("metadata updated")
            except Exception as me:
                logger.warning("metadata update (vectorized) failed: %s", me)

        return _done(True, t0, user_id, file_id, filename, effective_mode, chunk_size, overlap, chunks=len(chunks))

    except Exception as e:
        logger.exception("index_document failed: %s", e)
        if metadata_repo:
            try:
                await metadata_repo.mark_failed(file_id, str(e))
            except Exception:
                pass
        await _safe_emit(emit_event, "file.error", {
            "id": file_id,
            "message": str(e),
        })
        return _done(False, t0, user_id, file_id, filename, effective_mode, chunk_size, overlap, error=str(e))


# --- helpers ----------------------------------------------------------------

def _done(
    ok: bool,
    t0: float,
    user_id: str,
    file_id: str,
    filename: str,
    mode: ChunkMode,
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