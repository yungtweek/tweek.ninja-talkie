from __future__ import annotations

from typing import Protocol, List, AsyncIterator
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import RunnableConfig


class LlmPort(Protocol):
    """
    도메인에서 사용하는 LLM 포트.

    단발 응답(chat)과 스트리밍(chat_stream) 둘 다 지원.
    RAG는 이 포트를 통해 LLM만 호출하면 됨.
    """

    async def ainvoke(self, messages: List[BaseMessage], config: RunnableConfig | None = None, ) -> BaseMessage:
        """일반 ChatCompletion 요청."""
        ...

    async def astream(self, messages: List[BaseMessage], config: RunnableConfig | None = None, ) -> None:
        """스트리밍 ChatCompletion (deltaText 단위로 yield)."""
        ...
