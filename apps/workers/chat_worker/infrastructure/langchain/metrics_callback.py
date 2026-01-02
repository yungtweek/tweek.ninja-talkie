from __future__ import annotations

from time import monotonic
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from uuid import uuid4

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from chat_worker.logging_setup import get_logger

logger = get_logger(str(__name__))


def _messages_to_prompt_strings(messages: List[BaseMessage]) -> List[str]:
    """Convert chat messages to plain strings for token estimation."""
    prompts: List[str] = []
    for m in messages or []:
        try:
            prompts.append(str(getattr(m, "content", m)))
        except Exception:
            prompts.append(str(m))
    return prompts


def _as_int(value: Any) -> Optional[int]:
    """Best-effort cast to int; returns None when conversion fails."""
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None

def _has_tool_calls(response: LLMResult) -> bool:
    """Best-effort detection of tool calls in a LangChain LLMResult."""
    try:
        for gen_group in response.generations or []:
            for gen in gen_group:
                msg = getattr(gen, "message", None)
                if not msg:
                    continue
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    return True
                additional = getattr(msg, "additional_kwargs", None) or {}
                if additional.get("tool_calls") or additional.get("function_call"):
                    return True
    except Exception:
        return False
    return False

def parse_llmresult_metadata(response: LLMResult) -> Dict[str, Any]:
    """
    Extract model_name and token usage from LangChain LLMResult.

    Supports ChatOpenAI / GPT-5 style responses where usage metadata
    lives inside ChatGenerationChunk.message.
    """

    model_name: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    total_tokens: Optional[int] = None

    # 0️⃣ llm_output token usage (our vLLM worker path)
    try:
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            # Prefer explicit model name when present
            if not model_name:
                model_name = llm_output.get("model_name") or model_name

            usage_root = (
                llm_output.get("token_usage")
                or llm_output.get("usage")
                or llm_output
            )
            if isinstance(usage_root, dict):
                # Normalize keys across providers
                tokens_in = (
                    usage_root.get("prompt_tokens")
                    or usage_root.get("input_tokens")
                    or tokens_in
                )
                tokens_out = (
                    usage_root.get("completion_tokens")
                    or usage_root.get("output_tokens")
                    or tokens_out
                )
                total_tokens = usage_root.get("total_tokens") or total_tokens
    except Exception:
        # Best-effort only; fall back to generation parsing
        pass

    # LLMResult.generations: List[List[ChatGeneration | ChatGenerationChunk]]
    for gen_group in response.generations or []:
        for gen in gen_group:
            msg = getattr(gen, "message", None)
            if not msg:
                continue

            # 1️⃣ model name
            meta = getattr(msg, "response_metadata", None) or {}
            if not model_name:
                model_name = meta.get("model_name")

            # 2️⃣ token usage
            usage = getattr(msg, "usage_metadata", None) or {}
            gen_info = getattr(gen, "generation_info", None) or {}
            if not usage and gen_info:
                usage = {
                    "input_tokens": gen_info.get("prompt_tokens"),
                    "output_tokens": gen_info.get("completion_tokens"),
                    "total_tokens": gen_info.get("total_tokens"),
                }
            if usage:
                tokens_in = usage.get("input_tokens", tokens_in)
                tokens_out = usage.get("output_tokens", tokens_out)
                total_tokens = usage.get("total_tokens", total_tokens)

        # 하나만 잡으면 충분
        if model_name or tokens_in or tokens_out:
            break

    return {
        "model_name": model_name,
        "prompt_tokens": _as_int(tokens_in),
        "completion_tokens": _as_int(tokens_out),
        "total_tokens": _as_int(total_tokens),
    }


class MetricsCallback(AsyncCallbackHandler):
    """
    LangChain AsyncCallbackHandler implementation (metrics collection skeleton)

    - Inject into runners like run_llm_stream() for per-job metrics tracking.
    - Accumulates token counts, latency, and error codes per job.
    - Optional external sinks (Prometheus, logs, Redis, etc.) can be attached.
    - If `persist` is provided, metrics are written asynchronously to a persistent store.

    Usage:
        cb = MetricsCallback(job_id, mode='gen', provider='openai', model='gpt-4o-mini', sink=async_sink)
        await llm.ainvoke(messages, {"callbacks": [cb]})

        # Example: tiktoken-based counter
        # import tiktoken
        # enc = tiktoken.encoding_for_model('gpt-4o-mini')
        # cb = MetricsCallback(job_id, token_len=lambda s: len(enc.encode(s)))
    """

    def __init__(
            self,
            job_id: str,
            *,
            mode: str = "gen",
            span_name: str = "text",
            provider: Optional[str] = None,
            model: Optional[str] = None,
            sink: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
            persist: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
            token_len: Optional[Callable[[str], int]] = None,
            allowed_tags: Optional[Set[str]] = None,
            queue_ms: Optional[int] = None,
            first_token_delta_ms: Optional[Callable[[], Awaitable[Optional[int]]]] = None,
    ) -> None:
        self.job_id = job_id
        self.trace_id = job_id
        self.parent_span_id = job_id
        self._span_id: Optional[str] = None
        self.mode = mode
        self.span_name = span_name
        self.provider = provider
        self.model = model
        self.sink = sink
        self.persist = persist
        self.token_len = token_len  # text -> token count (e.g., via tiktoken/transformers)
        self._queue_ms: Optional[int] = queue_ms
        self._first_token_delta_ms = first_token_delta_ms
        self._rag_ms: Optional[int] = None

        # Only record metrics for runs that include at least one of these tags (e.g., {"final_answer"})
        self.allowed_tags: Optional[Set[str]] = set(allowed_tags) if allowed_tags else None
        # Track run_ids we decided to record (since a single callback instance may observe multiple runs)
        self._tracked_run_ids: Set[str] = set()

        # runtime state
        self._started_at: Optional[float] = None
        self._finished: bool = False
        self._tokens_in: int = 0
        self._tokens_out: int = 0
        self._error_code: Optional[str] = None
        self._first_token_at: Optional[float] = None
        self._published_to_first_token_ms: Optional[int] = None
        self._gen_parts: List[str] = []
        self._prompt_tokenized: bool = False

    # -------- helpers --------
    def snapshot(self) -> Dict[str, Any]:
        """Return current collection state as dict (for logging or external sync)."""
        now = monotonic()
        latency_ms = (
            int((now - self._started_at) * 1000) if self._started_at else None
        )
        ttft_ms = (
            int((self._first_token_at - self._started_at) * 1000)
            if self._started_at and self._first_token_at
            else None
        )
        gen_time_ms = (
            int((now - self._first_token_at) * 1000)
            if self._first_token_at and self._finished
            else None
        )
        tps = None
        if gen_time_ms and gen_time_ms > 0:
            tps = self._tokens_out / (gen_time_ms / 1000)
        return {
            "jobId": self.job_id,
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model,
            "tokensIn": self._tokens_in,
            "tokensOut": self._tokens_out,
            "latencyMs": latency_ms,
            "ttftMs": ttft_ms,
            "genTimeMs": gen_time_ms,
            "queueMs": self._queue_ms,
            "publishedToFirstTokenMs": self._published_to_first_token_ms,
            "ragMs": self._rag_ms,
            "tps": tps,
            "finished": self._finished,
            "errorCode": self._error_code,
        }

    def set_rag_ms(self, rag_ms: Optional[int]) -> None:
        if rag_ms is None:
            return
        self._rag_ms = rag_ms

    async def _emit(self, event: str) -> None:
        """Send metrics to external sink (fallback to log if none provided)."""
        payload = {"event": f"metrics.{event}", **self.snapshot()}
        logger.debug("emitting metrics: %s", payload)
        if self.sink:
            try:
                await self.sink(payload)
            except Exception as e:
                # Sink failure does not block service flow
                logger.warning("metrics sink failed: %s", e)

    async def _persist(self) -> None:
        """Persist metrics asynchronously via provided adapter (if available)."""
        if not self.persist:
            return
        snap = self.snapshot()
        latency_ms = snap.get("latencyMs")
        queue_ms = snap.get("queueMs")
        published_to_first_token_ms = snap.get("publishedToFirstTokenMs")
        rag_ms = snap.get("ragMs")
        total_ms = None
        if latency_ms is not None:
            total_ms = latency_ms + (queue_ms or 0) + (rag_ms or 0)
        span_id = self._span_id or str(uuid4())
        row = {
            "request_id": self.job_id,
            "trace_id": self.trace_id,
            "span_id": span_id,
            "parent_span_id": self.parent_span_id,
            "span_name": self.span_name,
            "user_id": None,
            "request_tag": "llm:request:chat",
            "provider": self.provider or "unknown",
            "model_name": self.model or "unknown",
            "model_path": "unknown",
            "use_rag": (self.mode == "rag"),
            "rag_hits": 0,
            "count_eot": True,
            "prompt_chars": 0,
            "prompt_tokens": snap.get("tokensIn", 0) or 0,
            "output_chars": 0,
            "completion_tokens": snap.get("tokensOut", 0) or 0,
            "ttft_ms": snap.get("ttftMs"),
            "gen_time_ms": snap.get("genTimeMs"),
            "queue_ms": queue_ms,
            "published_to_first_token_ms": published_to_first_token_ms,
            "rag_ms": rag_ms,
            "total_ms": total_ms,
            "tok_per_sec": snap.get("tps"),
            "response_status": 0 if self._error_code is None else 2,
            "error_message": None if self._error_code is None else self._error_code,
        }
        try:
            await self.persist(row)
        except Exception as e:
            # Persistence failure should not interrupt main execution
            logger.warning("metrics persist failed: %s", e)

    # -------- LLM lifecycle hooks --------
    async def on_chat_model_start(
            self,
            serialized: Dict[str, Any],
            messages: List[BaseMessage],
            **kwargs: Any,
    ) -> None:
        # Bridge chat events to llm events for compatibility with ChatOpenAI, etc.
        prompts = _messages_to_prompt_strings(messages)
        await self.on_llm_start(serialized, prompts, **kwargs)

    async def on_llm_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        run_id = kwargs.get("run_id")
        tags = kwargs.get("tags") or []
        if self.allowed_tags is not None:
            # Only track runs that contain any allowed tag
            if any(t in self.allowed_tags for t in tags):
                if run_id:
                    self._tracked_run_ids.add(str(run_id))
            else:
                # Not tracking this run; return early
                return
        elif run_id:
            # If no filter provided, track all runs
            self._tracked_run_ids.add(str(run_id))

        self._span_id = str(uuid4())
        self._started_at = monotonic()
        self._finished = False
        self._tokens_in = 0
        self._tokens_out = 0
        self._error_code = None
        self._first_token_at = None
        self._published_to_first_token_ms = None
        self._gen_parts = []
        self._prompt_tokenized = False
        # Update model name if provider supplies it
        model_name = (serialized or {}).get("name")
        if model_name:
            self.model = self.model or model_name
        # Estimate input tokens if tokenizer is provided (provider-dependent)
        if self.token_len is not None and not self._prompt_tokenized:
            try:
                # prompts is a list[str]; join conservatively with newline
                joined = "\n".join(prompts or [])
                self._tokens_in = self.token_len(joined)
                self._prompt_tokenized = True
            except Exception:
                self._tokens_in = self._tokens_in or 0
        else:
            self._tokens_in = self._tokens_in or 0
        await self._emit("start")

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        if run_id and str(run_id) not in self._tracked_run_ids:
            return

        # Record first token arrival time
        if self._first_token_at is None:
            self._first_token_at = monotonic()
            if self._first_token_delta_ms is not None:
                try:
                    self._published_to_first_token_ms = await self._first_token_delta_ms()
                except Exception as e:
                    logger.warning("metrics first token DB timing failed: %s", e)

        # NOTE: provider token callbacks may deliver partial text chunks that don't map 1:1 to model tokens.
        # Accumulate raw pieces and compute true token length at end using the configured tokenizer.
        self._gen_parts.append(token or "")
        # Per-token emission can be excessive; left disabled by default (uncomment to enable)
        # await self._emit("token")

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        if run_id and str(run_id) not in self._tracked_run_ids:
            return

        # Some providers return usage info → can adjust in/out token counts
        try:
            parsed = parse_llmresult_metadata(response)
            logger.debug("parsed llm metadata: %s", parsed)
            usage_root = getattr(response, "llm_output", None) or {}
            token_usage = usage_root.get("token_usage") or usage_root.get("usage") or usage_root or {}

            # Prefer model name from provider response; fall back to parsed
            model_from_resp = usage_root.get("model_name") or parsed.get("model_name")
            if model_from_resp:
                self.model = model_from_resp

            prompt_val = (
                token_usage.get("prompt_tokens")
                or token_usage.get("input_tokens")
                or parsed.get("prompt_tokens")
            )
            comp_val = (
                token_usage.get("completion_tokens")
                or token_usage.get("output_tokens")
                or parsed.get("completion_tokens")
            )
            total_val = token_usage.get("total_tokens") or parsed.get("total_tokens")

            prompt = _as_int(prompt_val)
            comp = _as_int(comp_val)
            total = _as_int(total_val)

            if prompt is not None and prompt >= self._tokens_in:
                self._tokens_in = prompt
            if comp is not None and comp >= self._tokens_out:
                self._tokens_out = comp
            if total is not None:
                # Fill whichever side is missing using total - known side
                if comp is None and prompt is not None and total >= prompt:
                    derived_out = total - prompt
                    if derived_out >= self._tokens_out:
                        self._tokens_out = derived_out
                if prompt is None and comp is not None and total >= comp:
                    derived_in = total - comp
                    if derived_in >= self._tokens_in:
                        self._tokens_in = derived_in
        except Exception:
            pass

        # Recompute with tokenizer when available to correct streaming approximations
        if self.token_len is not None:
            try:
                generated = "".join(self._gen_parts)
                out_len = self.token_len(generated)
                if not isinstance(self._tokens_out, int) or self._tokens_out == 0 or out_len > self._tokens_out:
                    self._tokens_out = out_len
            except Exception:
                pass

        self._finished = True
        if self.span_name == "text" and _has_tool_calls(response):
            self.span_name = "tool_call"
        await self._emit("done")
        await self._persist()

        if run_id:
            self._tracked_run_ids.discard(str(run_id))

    async def on_chat_model_end(self, response: LLMResult, **kwargs: Any) -> None:
        # Bridge chat events to llm events for compatibility
        await self.on_llm_end(response, **kwargs)

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        if run_id and str(run_id) not in self._tracked_run_ids:
            return

        self._error_code = type(error).__name__
        await self._emit("error")
        await self._persist()

        if run_id:
            self._tracked_run_ids.discard(str(run_id))

    async def on_chat_model_error(self, error: BaseException, **kwargs: Any) -> None:
        # Bridge chat events to llm events for compatibility
        await self.on_llm_error(error, **kwargs)
