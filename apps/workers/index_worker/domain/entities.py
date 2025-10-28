from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence
from .values import ChunkText, Embedding

@dataclass
class Document:
    id: str
    content: str
    created_at: datetime

@dataclass
class Chunk:
    id: str
    document_id: str
    order: int
    text: ChunkText
    embedding: Embedding | None = None
    meta: dict[str, str] = field(default_factory=dict)