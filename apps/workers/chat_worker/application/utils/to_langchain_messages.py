

"""
Utility to convert domain Turns (role/content pairs)
into LangChain message objects.
"""

from typing import Sequence, Mapping, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage


def to_langchain_messages(
    system_prompt: str,
    turns: Sequence[Mapping[str, Any]],
    user_input: str,
) -> list[BaseMessage]:
    """
    Convert a sequence of turns (domain objects) into LangChain message objects.

    Args:
        system_prompt: The system-level instruction string.
        turns: Sequence of {'role': 'user'|'assistant'|'system', 'content': str}
        user_input: Latest user message content.

    Returns:
        List of LangChain Message objects in proper conversation order.
    """
    msgs: List[BaseMessage] = [SystemMessage(content=system_prompt)]
    for t in turns:
        role = t.get("role")
        content = str(t.get("content", ""))
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
        else:
            msgs.append(SystemMessage(content=content))

    # add the new human input at the end
    msgs.append(HumanMessage(content=user_input))
    return msgs