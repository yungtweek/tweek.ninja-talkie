# chat_worker/application/services/chat_history_service.py
from typing import Sequence

from chat_worker.domain.ports.history import HistoryRepository, Turn

class HistoryService:
    def __init__(
            self,
            history_repo: HistoryRepository,
            system_prompt: str,
            max_ctx_tokens: int = 6000,
            max_history_turns: int = 12,
    ):
        self.history = history_repo
        self.system_prompt = system_prompt
        self.max_ctx_tokens = max_ctx_tokens
        self.max_history_turns = max_history_turns

    async def handle(self, user_id: str, session_id: str) -> Sequence[Turn]:
        turns = await self.history.load(user_id, session_id, limit=self.max_history_turns)
        return turns
