# chat_worker/application/utils/tokens.py
from typing import Sequence, Mapping, Any

def rough_token_count(text: str) -> int:
    return max(1, len(text) // 4)

def messages_token_count(msgs: Sequence[Mapping[str, Any]]) -> int:
    return sum(rough_token_count(m.get("content", "")) + 4 for m in msgs) + 2