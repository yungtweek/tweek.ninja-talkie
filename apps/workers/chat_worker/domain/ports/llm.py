from __future__ import annotations

from typing import Protocol, List, Optional, Mapping, Sequence, Any
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import RunnableConfig


class LlmPort(Protocol):
    """
    LLM port used in the domain layer.

    Supports both single response (`chat`) and streaming (`chat_stream`).
    RAG logic should call the LLM only through this port.
    """
    provider: Optional[str]
    model: str

    async def ainvoke(
            self,
            messages: List[BaseMessage],
            config: RunnableConfig | None = None,
            tools: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> BaseMessage:
        """Standard ChatCompletion request (single response)."""
        ...

    async def astream(
            self,
            messages: List[BaseMessage],
            config: RunnableConfig | None = None,
            tools: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> None:
        """
        Streaming ChatCompletion.

        Implementations should consume/drain the underlying stream and surface
        output via callbacks; callers only `await` completion and do not iterate
        over the stream directly.
        """
        ...
