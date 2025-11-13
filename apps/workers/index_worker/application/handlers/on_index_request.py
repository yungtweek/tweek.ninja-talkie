from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Literal, cast, Awaitable, Callable, Optional

from ..use_cases.index_document import IndexDocumentUseCase, IndexDocumentCommand
from ..chunking.base import ChunkMode, DEFAULT_CHUNK_MODE

@dataclass
class IndexRequestHandler:
    use_case: IndexDocumentUseCase

    async def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:

        cmd = IndexDocumentCommand(
            user_id=payload["user_id"],
            file_id=payload["file_id"],
            filename=payload["filename"],
            raw_bytes=payload["raw_bytes"],
            embedding_model=payload.get("embedding_model"),
            chunk_mode=cast(ChunkMode, payload.get("chunk_mode", DEFAULT_CHUNK_MODE)),
            chunk_size=payload.get("chunk_size", 500),
            overlap=payload.get("overlap", 50),
        )
        result = await self.use_case.execute(cmd)
        return dict(result)