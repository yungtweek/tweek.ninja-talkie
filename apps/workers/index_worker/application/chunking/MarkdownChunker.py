from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from dataclasses import dataclass
from typing import Sequence

from index_worker.application.chunking.base import BaseChunker, ChunkingInput, ChunkerMode
from index_worker.domain.entities import Chunk
from index_worker.domain.values import ChunkText


def _deterministic_id(*parts: str) -> str:
    """Build a deterministic identifier by hashing the given string parts."""
    h = hashlib.sha1()
    for p in parts:
        if p is None:
            p = ""
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()

@dataclass
class _SectionInfo:
    title: str | None
    level: int | None


class MarkdownChunker(BaseChunker):
    mode: ChunkerMode = "markdown"

    @staticmethod
    def _flush_buf(
        buf: list[str],
        blocks: list[str],
        block_section_titles: list[str | None],
        block_section_levels: list[int | None],
        *,
        section_title: str | None,
        section_level: int | None,
    ) -> None:
        block = "\n".join(buf).strip()
        if block:
            blocks.append(block)
            block_section_titles.append(section_title)
            block_section_levels.append(section_level)
        buf.clear()

    @staticmethod
    def _split_large_code_blocks(
        blocks: list[str],
        block_section_titles: list[str | None],
        block_section_levels: list[int | None],
        chunk_size: int,
    ) -> tuple[list[str], list[str | None], list[int | None]]:
        """Split very large fenced code blocks into smaller blocks by line.

        This keeps individual chunks from being dominated by a single huge code block,
        while still preserving code formatting (we split only on line boundaries).
        """
        if chunk_size <= 0:
            return blocks, block_section_titles, block_section_levels

        max_block_words = chunk_size * 4  # consider "very large" if > 4x chunk_size
        target_block_words = chunk_size * 2  # try to keep each sub-block around 2x

        new_blocks: list[str] = []
        new_titles: list[str | None] = []
        new_levels: list[int | None] = []

        for block, title, level in zip(blocks, block_section_titles, block_section_levels):
            stripped = block.lstrip()

            # Only consider fenced code blocks for this split.
            if stripped.startswith("```") or stripped.startswith("~~~"):
                words = block.split()
                if len(words) > max_block_words:
                    lines = block.split("\n")
                    current_lines: list[str] = []
                    current_words = 0

                    for line in lines:
                        line_word_count = len(line.split())
                        # if adding this line would exceed our target, flush current sub-block
                        if current_lines and current_words + line_word_count > target_block_words:
                            new_blocks.append("\n".join(current_lines))
                            new_titles.append(title)
                            new_levels.append(level)
                            current_lines = []
                            current_words = 0

                        current_lines.append(line)
                        current_words += line_word_count

                    if current_lines:
                        new_blocks.append("\n".join(current_lines))
                        new_titles.append(title)
                        new_levels.append(level)
                    continue  # done with this block, move to next

            # non-code or not too large: keep as-is
            new_blocks.append(block)
            new_titles.append(title)
            new_levels.append(level)

        return new_blocks, new_titles, new_levels

    def chunk(
        self,
        inp: ChunkingInput,
        *,
        chunk_size: int = 256,
        overlap: int = 32,
    ) -> Sequence[Chunk]:
        """Chunk markdown text into RAG-friendly pieces.

        Strategy (v1):
        - Normalize newlines.
        - Split into logical markdown blocks (headings / paragraphs / code blocks).
        - Within each block, apply a simple word-based sliding window with overlap.
        """
        text = (inp.text or "").strip()
        if not text:
            return []

        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if overlap < 0:
            overlap = 0
        if overlap >= chunk_size:
            overlap = max(0, chunk_size // 5)  # keep forward progress

        # 1) Normalize newlines
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")

        # 2) Split into markdown-aware blocks
        blocks: list[str] = []
        buf: list[str] = []
        in_code = False

        block_section_titles: list[str | None] = []
        block_section_levels: list[int | None] = []
        current_section_title: str | None = None
        current_section_level: int | None = None

        for raw_line in normalized.split("\n"):
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            # fenced code block start/end
            if stripped.startswith("```") or stripped.startswith("~~~"):
                # entering a code block: flush any pending paragraph/content
                if not in_code and buf:
                    self._flush_buf(
                        buf,
                        blocks,
                        block_section_titles,
                        block_section_levels,
                        section_title=current_section_title,
                        section_level=current_section_level,
                    )

                in_code = not in_code
                buf.append(line)

                # closing fence -> flush code block as its own block
                if not in_code:
                    self._flush_buf(
                        buf,
                        blocks,
                        block_section_titles,
                        block_section_levels,
                        section_title=current_section_title,
                        section_level=current_section_level,
                    )
                continue

            # already inside a fenced code block: keep lines verbatim
            if in_code:
                buf.append(line)
                continue


            # heading line -> start a new section; attach heading to following content
            if stripped.startswith("#"):
                # flush any previous paragraph/content with the previous section info
                if buf:
                    self._flush_buf(
                        buf,
                        blocks,
                        block_section_titles,
                        block_section_levels,
                        section_title=current_section_title,
                        section_level=current_section_level,
                    )

                # parse heading level and title text
                hash_prefix = stripped.split(" ", 1)[0]
                level = len(hash_prefix)
                # strip leading '#' characters and whitespace to get the clean title
                title_text = stripped[level:].strip() if len(stripped) > level else stripped.lstrip("#").strip()

                current_section_title = title_text or stripped
                current_section_level = level

                # start a new buffer with the heading line itself;
                # it will be flushed together with the following content for this section
                buf.append(line)
                continue

            # blank line -> paragraph separator
            if stripped == "":
                if buf:
                    self._flush_buf(
                        buf,
                        blocks,
                        block_section_titles,
                        block_section_levels,
                        section_title=current_section_title,
                        section_level=current_section_level,
                    )
                continue

            # normal content line
            buf.append(line)

        if buf:
            self._flush_buf(
                buf,
                blocks,
                block_section_titles,
                block_section_levels,
                section_title=current_section_title,
                section_level=current_section_level,
            )

        # filter any accidental empties
        blocks = [b for b in blocks if b]

        if not blocks:
            return []

        # split overly large fenced code blocks into smaller, line-aligned blocks
        blocks, block_section_titles, block_section_levels = self._split_large_code_blocks(
            blocks,
            block_section_titles,
            block_section_levels,
            chunk_size,
        )

        # pre-compute total word count for metadata
        def _split_words(s: str) -> list[str]:
            return s.split()

        block_words_list: list[list[str]] = [_split_words(b) for b in blocks]
        total_words = sum(len(ws) for ws in block_words_list)
        if total_words == 0:
            return []

        # 3) Build chunks with simple word-based sliding window
        chunks: list[Chunk] = []
        idx = 0
        global_offset = 0  # word-based offset across entire document

        step = chunk_size - overlap
        if step <= 0:
            step = 1

        for block_idx, words in enumerate(block_words_list):
            n = len(words)
            if n == 0:
                continue

            local_start = 0
            while local_start < n:
                local_end = min(local_start + chunk_size, n)
                slice_words = words[local_start:local_end]
                chunk_text_str = " ".join(slice_words).strip()
                if chunk_text_str:
                    offset_start = global_offset + local_start
                    offset_end = global_offset + local_end

                    cid = _deterministic_id(
                        inp.file_id,
                        str(idx),
                        chunk_text_str[:64],
                        chunk_text_str[-64:],
                    )

                    meta = {
                        "file_id": inp.file_id,
                        "user_id": inp.user_id,
                        "filename": inp.filename,
                        "mode": self.mode,
                        "offset_start": str(offset_start),
                        "offset_end": str(offset_end),
                        "total_units": str(total_words),
                        "unit": "word",
                        "block_id": str(block_idx),
                        "block_local_start": str(local_start),
                        "block_local_end": str(local_end),
                    }
                    section_title = block_section_titles[block_idx] if block_section_titles else None
                    section_level = block_section_levels[block_idx] if block_section_levels else None
                    if section_title is not None:
                        meta["section_title"] = section_title
                    if section_level is not None:
                        meta["section_level"] = str(section_level)
                    if inp.page is not None:
                        meta["page"] = str(inp.page)

                    chunks.append(
                        Chunk(
                            id=cid,
                            document_id=inp.file_id,
                            chunk_index=idx,
                            text=ChunkText(chunk_text_str),
                            embedding=None,
                            meta=meta,
                        )
                    )
                    idx += 1

                if local_end >= n:
                    break
                local_start += step

            # advance global offset by full block size, regardless of how it was chunked
            global_offset += n

        return chunks