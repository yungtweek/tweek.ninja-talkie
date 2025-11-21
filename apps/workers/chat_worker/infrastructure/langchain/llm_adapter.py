# apps/workers/chat_worker/infrastructure/langchain/llm_adapter.py
from __future__ import annotations

from typing import List, AsyncIterator

import anyio
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import RunnableConfig

from chat_worker.domain.ports.llm import LlmPort
from chat_worker.settings import Settings
from chat_worker.infrastructure.langchain.openai_client import get_llm  # 지금은 OpenAI / 나중에 vLLM 쪽으로 교체 가능

_settings = Settings()


class LangchainLlmAdapter:
    """LlmPort implementation wrapping a LangChain ChatModel.

    Currently uses OpenAI via openai_client.get_llm().
    Can be replaced with vLLM or fallback client without changing domain code.
    """

    def __init__(
            self,
            model: str | None = None,
            temperature: float | None = None,
            timeout_s: int | None = None,
    ) -> None:
        self.model = model or _settings.LLM_MODEL
        self.temperature = temperature if temperature is not None else _settings.LLM_TEMPERATURE
        self.timeout_s = timeout_s if timeout_s is not None else _settings.LLM_TIMEOUT_S

    async def _get_llm(self):
        # Currently returns OpenAI client; can be swapped with vLLM or fallback client.
        return await get_llm(
            model=self.model,
            temperature=self.temperature,
            timeout_s=self.timeout_s,
        )

    async def ainvoke(
            self,
            messages: List[BaseMessage],
            config: RunnableConfig | None = None,
    ) -> BaseMessage:
        """Non-streaming ChatCompletion using LangChain ainvoke."""
        llm = await self._get_llm()

        if config is None:
            # Default behavior when no config is provided
            return await llm.ainvoke(messages)
        else:
            # Explicit config passthrough
            return await llm.ainvoke(messages, config)

    async def astream(
            self,
            messages: List[BaseMessage],
            config: RunnableConfig | None = None,
    ) -> None:
        """Streaming ChatCompletion wrapper that forwards chunks via LangChain callbacks."""
        llm = await self._get_llm()

        if config is None:
            astream = llm.astream(messages)
        else:
            astream = llm.astream(messages, config)

        async for _chunk in astream:
            # Token delivery is handled by TokenStreamCallback.on_llm_new_token
            continue