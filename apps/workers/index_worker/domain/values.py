from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Embedding:
    vector: tuple[float, ...]  # 불변
    def __post_init__(self):
        if not self.vector:
            raise ValueError("Embedding empty")

@dataclass(frozen=True)
class ChunkText:
    text: str
    def __post_init__(self):
        t = self.text.strip()
        if not t:
            raise ValueError("Chunk text empty")
        if len(t) > 8000:
            raise ValueError("Chunk text too long")