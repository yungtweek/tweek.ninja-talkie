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
    """LangChain ChatOpenAI(get_llm)을 감싼 LlmPort 구현체.

    - 지금은 OpenAI용 openai_client.get_llm()을 사용
    - 나중에 vLLM용 client나 FallbackChatModel로 교체해도,
      도메인에서는 LlmPort 인터페이스만 보면 되도록 설계
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
        # 지금은 openai_client.get_llm 을 사용하지만,
        # 나중에 vllm_client.get_llm 또는 fallback_client.get_llm 으로 바꿔도 됨.
        return await get_llm(
            model=self.model,
            temperature=self.temperature,
            timeout_s=self.timeout_s,
        )

    async def chat(
            self,
            messages: List[BaseMessage],
            config: RunnableConfig | None = None,
    ) -> BaseMessage:
        """일반 ChatCompletion (non-stream, LangChain ainvoke 사용)."""
        llm = await self._get_llm()

        if config is None:
            # 기존처럼 기본 설정
            return await llm.ainvoke(messages)
        else:
            # 예전 코드: await llm.ainvoke(messages, config)
            return await llm.ainvoke(messages, config)

    async def chat_stream(
            self,
            messages: List[BaseMessage],
            config: RunnableConfig | None = None,
    ) -> None:
        """스트리밍 ChatCompletion.

        LangChain ChatModel의 astream()을 감싸서 delta text만 흘려보낸다.
        """
        llm = await self._get_llm()

        if config is None:
            astream = llm.astream(messages)
        else:
            astream = llm.astream(messages, config)

        async for _chunk in astream:
            # 실제 토큰 전송은 TokenStreamCallback.on_llm_new_token이 담당
            continue