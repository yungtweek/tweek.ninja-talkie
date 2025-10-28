# apps/workers/chat_worker/service/openai_client.py
from __future__ import annotations
import asyncio
from typing import Dict, Tuple, Optional, Iterable, Any

from langchain_openai import ChatOpenAI  # LangChain 0.2+ 권장
from chat_worker.settings import Settings

_settings = Settings()
_lock = asyncio.Lock()
_registry: Dict[Tuple[str, float, Optional[int]], ChatOpenAI] = {}


def _make_key(model: str, temperature: float, timeout_s: Optional[int]) -> Tuple[str, float, Optional[int]]:
    return model, temperature, timeout_s


def _create_llm(model: str, temperature: float, timeout_s: Optional[int]) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        streaming=True,
        timeout=timeout_s,
    )


async def get_llm(
        model: Optional[str] = None,
        *,
        temperature: Optional[float] = None,
        timeout_s: Optional[int] = None,
) -> ChatOpenAI:
    m = model or _settings.LLM_MODEL
    t = temperature if temperature is not None else _settings.LLM_TEMPERATURE
    to = timeout_s if timeout_s is not None else _settings.LLM_TIMEOUT_S

    key = _make_key(m, t, to)
    if key in _registry:
        return _registry[key]

    async with _lock:
        if key in _registry:
            return _registry[key]
        llm = _create_llm(m, t, to)
        _registry[key] = llm
        return llm


async def warmup(messages: Optional[Iterable[Any]] = None) -> None:
    llm = await get_llm()
    _ = llm  # no-op
