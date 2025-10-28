"""
Message Builder Utility for Chat Worker
- Constructs the final message list (system + history + user input) within the model's context token limit.
- Preserves chronological order while backfilling history until token budget is exhausted.
"""
from typing import Sequence, Mapping, Any, List
from .tokens import messages_token_count

def build_messages(
        system_prompt: str,
        history: Sequence[Mapping[str, Any]],  # [{role, content, created_at}]
        user_input: str,
        max_ctx_tokens: int,
) -> List[dict]:
    """
    Build a list of messages for the LLM within a given token budget.

    Parameters:
    - system_prompt: System instruction message prepended to every chat.
    - history: Sequence of prior messages with roles and content (newest last).
    - user_input: Current user message.
    - max_ctx_tokens: Maximum context length allowed for the model.

    Returns:
    - List[dict] containing system, selected history, and current user message.

    Behavior:
    - Iterates backward through history (most recent first).
    - Adds messages until token count exceeds max_ctx_tokens.
    - Maintains message order required by the LLM API.
    """
    msgs: List[dict] = [{"role": "system", "content": system_prompt}]
    acc: List[dict] = []

    # History is assumed to be chronological (oldest → newest); we iterate in reverse to fill backward.
    for t in reversed(history):
        # Try adding one more previous message to the accumulator.
        candidate = [{"role": t["role"], "content": t["content"]}] + acc
        # Compose a temporary list including system, accumulated history, and the new user input to measure token count.
        test = [{"role": "system", "content": system_prompt}] + candidate + [{"role": "user", "content": user_input}]
        # If within token budget, accept the candidate; otherwise, stop adding more history.
        if messages_token_count(test) <= max_ctx_tokens:
            acc = candidate
        else:
            break

    # Append accepted history in correct order after system prompt.
    msgs += acc
    # Finally, append the current user message.
    msgs.append({"role": "user", "content": user_input})
    return msgs