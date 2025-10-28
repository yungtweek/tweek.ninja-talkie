"""
Chunking utilities for the indexing worker.
- Normalizes raw text and splits it into RAG-friendly chunks.
- Supports word/char/token modes with optional overlap.
- Produces deterministic chunk IDs for idempotent re-processing.
"""

import uuid
import hashlib
import tiktoken

from datetime import datetime, UTC
from typing import Literal

from index_worker.domain.entities import Chunk
from index_worker.domain.values import ChunkText


def _normalize_text(src: str) -> str:
    """
    Normalize text for chunking.
    - Converts CRLF/CR to LF, then replaces newlines with spaces.
    - Collapses multiple spaces to a single space and trims.
    """
    # Normalize whitespace/newlines: collapse newlines to spaces and reduce runs of spaces
    s = src.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", " ")
    # Collapse multiple spaces to a single space
    return " ".join(s.split()).strip()


def _deterministic_id(*parts: str) -> str:
    """
    Build a deterministic identifier by hashing the given string parts.
    - Uses SHA-1 over UTF-8 encoded parts separated by a null byte.
    - Suitable as a stable key for chunks (idempotent across runs).
    """
    h = hashlib.sha1()
    for p in parts:
        if p is None:
            p = ""
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    # SHA-1 hex is sufficient as a lookup key. If a UUIDv5 is preferred, use the commented line below.
    return h.hexdigest()
    # return str(uuid.uuid5(uuid.NAMESPACE_URL, h.hexdigest()))


def chunk_text(
    text: str,
    file_id: str,
    user_id: str,
    filename: str,
    *,
    chunk_size: int = 500,
    overlap: int = 50,
    mode: Literal["word", "char", "token"] = "word",
    page: int | None = None,
) -> list[Chunk]:
    """
    Convert raw text into an array of RAG chunks with metadata.

    Parameters:
    - text: Source text to chunk.
    - file_id: Logical document/file id the chunks belong to.
    - user_id: Owner of the document (used in metadata).
    - filename: Original filename for trace/debug.
    - chunk_size: Target units per chunk (word/char/token depending on mode).
    - overlap: Context overlap between consecutive chunks (0 <= overlap < chunk_size).
    - mode: One of 'word' | 'char' | 'token'.
    - page: Optional source page number (if available).

    Returns:
    - List[Chunk] with deterministic ids and per-chunk metadata.
    """
    # Defensive checks for parameters
    if not isinstance(text, str):
        raise TypeError("chunk_text: text must be str")
    if chunk_size <= 0:
        raise ValueError("chunk_text: chunk_size must be > 0")
    if overlap < 0:
        overlap = 0
    if overlap >= chunk_size:
        # Clamp overlap to ~20% of chunk_size to keep forward progress
        overlap = max(0, chunk_size // 5)

    # Pre-normalize text to improve tokenizer stability
    norm = _normalize_text(text)
    if not norm:
        return []

    chunks: list[Chunk] = []
    idx = 0

    # Token-based chunking using tiktoken (OpenAI cl100k_base)
    if mode == "token":
        # Use a stable tokenizer to ensure consistent token boundaries
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(norm)
        total = len(tokens)
        # Sliding window step preserves the specified overlap
        step = chunk_size - overlap
        for start in range(0, total, step):
            end = min(start + chunk_size, total)
            sub_tokens = tokens[start:end]
            chunk_text_str = enc.decode(sub_tokens).strip()
            if not chunk_text_str:
                continue

            # Derive a deterministic id from file_id, index, and text edges
            cid = _deterministic_id(file_id, str(idx), chunk_text_str[:64], chunk_text_str[-64:])

            # Minimal, searchable metadata attached to each chunk
            meta = {
                "file_id": file_id,
                "user_id": user_id,
                "filename": filename,
                "mode": mode,
                "offset_start": str(start),
                "offset_end": str(end),
                "total_units": str(total),
                "unit": "token",
                "created_at": datetime.now(UTC),
            }
            if page is not None:
                meta["page"] = str(page)

            chunks.append(
                Chunk(
                    id=cid,
                    document_id=file_id,
                    order=idx,
                    text=ChunkText(chunk_text_str),
                    embedding=None,
                    meta=meta,
                )
            )
            idx += 1
        return chunks

    # word/char mode: split by spaces or into characters
    units = norm.split() if mode == "word" else list(norm)
    total = len(units)
    step = chunk_size - overlap

    for start in range(0, total, step):
        end = min(start + chunk_size, total)
        unit_slice = units[start:end]
        # Reconstruct chunk text from the selected unit slice
        chunk_text_str = (" ".join(unit_slice) if mode == "word" else "".join(unit_slice)).strip()
        if not chunk_text_str:
            continue

        # Derive a deterministic id from file_id, index, and text edges
        cid = _deterministic_id(file_id, str(idx), chunk_text_str[:64], chunk_text_str[-64:])

        # Minimal, searchable metadata attached to each chunk
        meta = {
            "file_id": file_id,
            "user_id": user_id,
            "filename": filename,
            "mode": mode,
            "offset_start": str(start),
            "offset_end": str(end),
            "total_units": str(total),
            "unit": "word" if mode == "word" else "char",
            "created_at": datetime.now(UTC),
        }
        if page is not None:
            meta["page"] = str(page)

        chunks.append(
            Chunk(
                id=cid,
                document_id=file_id,
                order=idx,
                text=ChunkText(chunk_text_str),
                embedding=None,
                meta=meta,
            )
        )
        idx += 1

    return chunks
