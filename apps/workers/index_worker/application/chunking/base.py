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

ChunkerMode = Literal["word", "char", "token", "markdown"]

class BaseChunker(ABC):
    """Common interface for all chunkers.

    Each chunker implements a specific strategy (word / char / token / markdown)
    and exposes its own `mode` attribute.

    Args:
        inp: Raw document + metadata for chunking.
        chunk_size: Target size per chunk in the chosen unit.
        overlap: Overlap size between adjacent chunks.
    """

    mode: ChunkerMode  # 각 구현체가 가져야 하는 속성

    @abstractmethod
    def chunk(
            self,
            inp: ChunkingInput,
            *,
            chunk_size: int = 256,
            overlap: int = 32,
    ) -> Sequence[Chunk]:
        ...