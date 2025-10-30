from __future__ import annotations

from logging import getLogger
from time import monotonic
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

logger = getLogger(__name__)


class MetricsCallback(AsyncCallbackHandler):
    """
    LangChain AsyncCallbackHandler implementation (metrics collection skeleton)

    - Inject into runners like run_llm_stream() for per-job metrics tracking.
    - Accumulates token counts, latency, and error codes per job.
    - Optional external sinks (Prometheus, logs, Redis, etc.) can be attached.
    - If `persist` is provided, metrics are written asynchronously to a persistent store.

    Usage:
        cb = MetricsCallback(job_id, mode='gen', model='gpt-4o-mini', sink=async_sink)
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
            model: Optional[str] = None,
            sink: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
            persist: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
            token_len: Optional[Callable[[str], int]] = None,
            allowed_tags: Optional[Set[str]] = None,
    ) -> None:
        self.job_id = job_id
        self.mode = mode
        self.model = model
        self.sink = sink
        self.persist = persist
        self.token_len = token_len  # text -> token count (e.g., via tiktoken/transformers)

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
            "model": self.model,
            "tokensIn": self._tokens_in,
            "tokensOut": self._tokens_out,
            "latencyMs": latency_ms,
            "ttftMs": ttft_ms,
            "genTimeMs": gen_time_ms,
            "tps": tps,
            "finished": self._finished,
            "errorCode": self._error_code,
        }

    async def _emit(self, event: str) -> None:
        """Send metrics to external sink (fallback to log if none provided)."""
        payload = {"event": f"metrics.{event}", **self.snapshot()}
        if self.sink:
            try:
                await self.sink(payload)
            except Exception as e:
                # Sink failure does not block service flow
                logger.warning("metrics sink failed: %s", e)
        else:
            logger.debug(payload)

    async def _persist(self) -> None:
        """Persist metrics asynchronously via provided adapter (if available)."""
        if not self.persist:
            return
        snap = self.snapshot()
        row = {
            "request_id": self.job_id,
            "trace_id": self.job_id,
            "span_id": self.job_id,
            "parent_span_id": None,
            "user_id": None,
            "request_tag": "llm:request:chat",
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
            "total_ms": snap.get("latencyMs"),
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
    def on_chat_model_start(
            self,
            *args,
            **kwargs: Any,
    ):
        # LangChain 0.2+ emits this event when an LLM starts
        # We don't need to do anything special here, just silence the warning
        pass

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

        self._started_at = monotonic()
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
            usage = getattr(response, "llm_output", None) or {}
            # Example: usage = {"token_usage": {"completion_tokens": 123, "prompt_tokens": 45}}
            token_usage = usage.get("token_usage") or usage.get("usage") or {}
            comp = token_usage.get("completion_tokens")
            prompt = token_usage.get("prompt_tokens")
            if isinstance(comp, int) and comp >= self._tokens_out:
                self._tokens_out = comp
            if isinstance(prompt, int) and prompt >= self._tokens_in:
                self._tokens_in = prompt
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
        await self._emit("done")
        await self._persist()

        if run_id:
            self._tracked_run_ids.discard(str(run_id))

    async def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        if run_id and str(run_id) not in self._tracked_run_ids:
            return

        self._error_code = type(error).__name__
        await self._emit("error")
        await self._persist()

        if run_id:
            self._tracked_run_ids.discard(str(run_id))
