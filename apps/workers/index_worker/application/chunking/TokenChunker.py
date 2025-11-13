from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import tiktoken
from dataclasses import dataclass
from typing import Sequence

from index_worker.application.chunking.base import BaseChunker, ChunkingInput, ChunkMode
from index_worker.application.chunking.helpers import deterministic_id, normalize_text
from index_worker.domain.entities import Chunk
from index_worker.domain.values import ChunkText




class TokenChunker(BaseChunker):
    mode: ChunkMode = "token"

    def chunk(
        self,
        inp: ChunkingInput,
        *,
        chunk_size: int = 256,
        overlap: int = 32,
    ) -> Sequence[Chunk]:
        """
        Token-based chunker backed by tiktoken.

        This replicates the previous `chunk_text(..., mode="token")` behavior on top of
        the BaseChunker interface so that token chunking can be used via the new factory.
        """

        text = inp.text
        file_id = inp.file_id
        user_id = inp.user_id
        filename = inp.filename
        page = inp.page

        # Defensive checks for parameters
        if not isinstance(text, str):
            raise TypeError("TokenChunker.chunk: text must be str")
        if chunk_size <= 0:
            raise ValueError("TokenChunker.chunk: chunk_size must be > 0")
        if overlap < 0:
            overlap = 0
        if overlap >= chunk_size:
            # Clamp overlap to ~20% of chunk_size to keep forward progress
            overlap = max(0, chunk_size // 5)

        # Pre-normalize text to improve tokenizer stability
        norm = normalize_text(text)
        if not norm:
            return []

        # Use a stable tokenizer to ensure consistent token boundaries
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(norm)
        total = len(tokens)
        if total == 0:
            return []

        # Sliding window step preserves the specified overlap
        step = chunk_size - overlap

        chunks: list[Chunk] = []
        idx = 0
        for start in range(0, total, step):
            end = min(start + chunk_size, total)
            sub_tokens = tokens[start:end]
            chunk_text_str = enc.decode(sub_tokens).strip()
            if not chunk_text_str:
                continue

            # Derive a deterministic id from file_id, index, and text edges
            cid = deterministic_id(
                file_id,
                str(idx),
                chunk_text_str[:64],
                chunk_text_str[-64:],
            )

            # Minimal, searchable metadata attached to each chunk
            meta: dict[str, str] = {
                "file_id": file_id,
                "user_id": user_id,
                "filename": filename,
                "mode": self.mode,
                "offset_start": str(start),
                "offset_end": str(end),
                "total_units": str(total),
                "unit": "token",
            }
            if page is not None:
                meta["page"] = str(page)

            chunks.append(
                Chunk(
                    id=cid,
                    document_id=file_id,
                    chunk_index=idx,
                    text=ChunkText(chunk_text_str),
                    embedding=None,
                    meta=meta,
                )
            )
            idx += 1

        return chunks