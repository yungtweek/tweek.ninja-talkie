# application/chunking/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, Sequence, Literal

from index_worker.domain.entities import Chunk


@dataclass
class ChunkingInput:
    text: str
    file_id: str
    user_id: str
    filename: str
    extension: str | None = None
    page: int | None = None

# Supported chunking modes across the application.
#
# - "word":  legacy word-based splitting (may be deprecated in favor of token-based).
# - "char":  legacy character-level splitting.
# - "token": default mode, aligned with the LLM tokenizer.
# - "markdown": structure-aware Markdown chunking.
ChunkMode = Literal["word", "char", "token", "markdown"]

# Global default chunking mode used when a caller does not explicitly specify one.
# Keeping this here avoids scattering hard-coded "token" literals across the codebase.
DEFAULT_CHUNK_MODE: ChunkMode = "token"

class BaseChunker(ABC):
    """Common interface for all chunkers.

    Each chunker implements a specific strategy (word / char / token / markdown)
    and exposes its own `mode` attribute.

    Args:
        inp: Raw document + metadata for chunking.
        chunk_size: Target size per chunk in the chosen unit.
        overlap: Overlap size between adjacent chunks.
    """

    mode: ChunkMode  # 각 구현체가 가져야 하는 속성

    @abstractmethod
    def chunk(
            self,
            inp: ChunkingInput,
            *,
            chunk_size: int = 256,
            overlap: int = 32,
    ) -> Sequence[Chunk]:
        ...