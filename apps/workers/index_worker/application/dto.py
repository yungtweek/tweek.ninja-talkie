from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class IndexCommand:
    user_id: str
    file_id: str
    filename: str
    raw_bytes: bytes | None
    embedding_model: str