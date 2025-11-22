# apps/workers/title_worker/domain/ports/session_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional, Tuple


class ChatSessionRepository(ABC):
    # -------------------------
    # Session Title
    # -------------------------
    @abstractmethod
    async def upsert_session_title(
            self,
            *,
            user_id: str,
            session_id: str,
            title: str,
    ) -> None:
        ...
