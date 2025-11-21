from __future__ import annotations

import asyncio
import logging
from typing import Dict, Tuple, Optional, Iterable, Any, List

import grpc
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from chat_worker.infrastructure.grpc_stubs.llm import llm_pb2_grpc, llm_pb2
from chat_worker.settings import Settings

logger = logging.getLogger(str(__name__))

_settings = Settings()
_lock = asyncio.Lock()
_registry: Dict[Tuple[str, str, Optional[int]], VllmGrpcClient] = {}


def _make_key(addr: str, model: str, timeout_ms: Optional[int]) -> Tuple[str, str, Optional[int]]:
    return addr, model, timeout_ms


def _messages_to_prompts(messages: List[BaseMessage]) -> tuple[str, str]:
    """Convert LangChain messages into (system_prompt, user_prompt) strings."""
    system_parts: list[str] = []
    user_parts: list[str] = []

    for m in messages:
        role = getattr(m, "type", None) or getattr(m, "role", None)
        content = m.content if isinstance(m.content, str) else str(m.content)

        if role in ("system", "system_message"):
            system_parts.append(content)
        elif role in ("human", "user", "human_message"):
            user_parts.append(content)
        else:
            # AI / 기타 롤은 일단 user 프롬프트 뒤에 메모처럼 붙이자
            user_parts.append(f"\n\n[prev {role}]: {content}")

    system_prompt = "\n\n".join(system_parts) if system_parts else ""
    user_prompt = "\n\n".join(user_parts) if user_parts else ""
    return system_prompt, user_prompt


class VllmGrpcClient:
    """gRPC client for the Go llm-gateway wrapper around vLLM."""

    def __init__(
            self,
            addr: str,
            model: str,
            timeout_ms: Optional[int],
    ) -> None:
        self.addr = addr
        self.model = model
        self.timeout_ms = timeout_ms

        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[llm_pb2_grpc.LlmServiceStub] = None

    async def _get_stub(self) -> llm_pb2_grpc.LlmServiceStub:
        if self._stub is None:
            # Future: switch to secure_channel when TLS is enabled
            self._channel = grpc.aio.insecure_channel(self.addr)
            self._stub = llm_pb2_grpc.LlmServiceStub(self._channel)

        return self._stub

    async def ainvoke(
            self,
            messages: List[BaseMessage],
            config: RunnableConfig | None = None,
    ) -> AIMessage:
        """Unary ChatCompletion request."""
        stub = await self._get_stub()
        system_prompt, user_prompt = _messages_to_prompts(messages)

        req = llm_pb2.ChatCompletionRequest(
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context="",
            temperature=_settings.LLM_TEMPERATURE,
            max_tokens=_settings.LLM_MAX_TOKENS,
            top_p=_settings.LLM_TOP_P,
        )

        timeout_s = (self.timeout_ms or _settings.LLM_TIMEOUT_MS) / 1000.0

        # unary RPC 호출
        resp = await stub.ChatCompletion(req, timeout=timeout_s)

        output_text = resp.output_text
        return AIMessage(content=output_text)

    async def astream(
            self,
            messages: List[BaseMessage],
            config: RunnableConfig | None = None,
    ) -> None:
        """Server‑streaming ChatCompletion that forwards chunks into LangChain callbacks."""
        stub = await self._get_stub()
        system_prompt, user_prompt = _messages_to_prompts(messages)

        req = llm_pb2.ChatCompletionRequest(
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context="",
            temperature=_settings.LLM_TEMPERATURE,
            max_tokens=_settings.LLM_MAX_TOKENS,
            top_p=_settings.LLM_TOP_P,
        )

        timeout_s = (self.timeout_ms or _settings.LLM_TIMEOUT_MS) / 1000.0
        callbacks = []
        tags: list[str] = []
        if config:
            # Extract tags/callbacks from RunnableConfig
            if isinstance(config, dict):
                callbacks = list(config.get("callbacks") or [])
                tags = list(config.get("tags") or [])
            else:
                callbacks = list(getattr(config, "callbacks", []) or [])
                tags = list(getattr(config, "tags", []) or [])

        async for chunk in stub.ChatCompletionStream(req, timeout=timeout_s):
            # proto stub를 신뢰하고 deltaText 필드를 직접 사용
            delta = chunk.deltaText
            if not delta:
                continue

            # 🔥 여기서 기존 TokenStreamCallback 시그니처에 맞춰서 호출
            for cb in callbacks:
                on_token = getattr(cb, "on_llm_new_token", None)
                if on_token is None:
                    continue

                # TokenStreamCallback은 run_coroutine_threadsafe 내부에서 쓰니까
                # 여기서는 그냥 await on_token(...) 해도 됨 (이미 async로 정의돼있음)
                await on_token(delta, tags=tags)

        # Trigger end‑of‑stream callbacks
        for cb in callbacks:
            on_end = getattr(cb, "on_llm_end", None)
            if on_end is not None:
                result = on_end(None, tags=tags)
                if asyncio.iscoroutine(result):
                    await result


def _create_client(
        addr: str,
        model: str,
        timeout_ms: Optional[int],
) -> VllmGrpcClient:
    return VllmGrpcClient(addr=addr, model=model, timeout_ms=timeout_ms)


async def get_llm(
        model: Optional[str] = None,
        *,
        temperature: Optional[float] = None,  # NOTE: 지금은 vLLM gateway 쪽 설정 우선, 필요하면 나중에 반영
        timeout_s: Optional[int] = None,
) -> VllmGrpcClient:
    """Factory for reusing vLLM gRPC clients (keyed by addr/model/timeout)."""
    addr = _settings.LLM_GATEWAY_ADDR
    m = model or _settings.LLM_DEFAULT_MODEL
    # temperature는 지금은 사용하지 않지만 시그니처 맞추기용으로 유지
    _ = temperature
    to_ms = (timeout_s or _settings.LLM_TIMEOUT_MS)

    logger.info("vLLM gRPC client config", extra={
        "addr": addr,
        "model": m,
        "timeout_ms": to_ms,
    })

    key = _make_key(addr, m, to_ms)
    if key in _registry:
        return _registry[key]

    async with _lock:
        if key in _registry:
            return _registry[key]
        client = _create_client(addr, m, to_ms)
        _registry[key] = client
        return client


async def warmup(messages: Optional[Iterable[Any]] = None) -> None:
    """Pre‑initialize the gRPC channel."""
    _ = messages
    client = await get_llm()
    _ = client  # no-op