"""
History Repository Port
- Defines how chat history (turns) is stored, retrieved, and summarized.
- Used by chat workers to load recent context and append assistant/user turns.
"""
from typing import Protocol, TypedDict, Literal, Sequence

# Valid roles for chat turns
Role = Literal["system", "user", "assistant"]

class Turn(TypedDict):
    """
    A single conversational turn in the chat history.
    - role: system/user/assistant
    - content: raw text
    - created_at: Unix epoch timestamp (float)
    """
    role: Role
    content: str
    created_at: float  # epoch

class HistoryRepository(Protocol):
    """
    Protocol (port) for accessing and mutating chat history.
    - Provides context for LLM prompts and allows persistence of new messages.
    - Implementations may store data in Postgres, Redis, or any persistent store.
    """

    async def load(self, user_id: str, session_id: str, limit: int) -> Sequence[Turn]:
        """
        Load the most recent chat turns up to the given limit.
        Ordered chronologically (oldest → newest).
        """
        ...

    async def load_all(self, user_id: str, session_id: str) -> Sequence[Turn]:
        """
        Load the full conversation history for a given session.
        May be used for summarization or analytics.
        """
        ...

    async def append(self, user_id: str, session_id: str, role: Role, content: str) -> None:
        """
        Append a new message (user or assistant) to the session history.
        Implementations should preserve insertion order and timestamps.
        """
        ...

    async def replace_summary(self, user_id: str, session_id: str, summary: str) -> None:
        """
        Replace or update the session summary text.
        Used after summarization runs to compress long histories.
        """
        ...