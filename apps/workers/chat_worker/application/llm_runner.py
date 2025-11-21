"""
LLM Runner (Chat Worker)
- Executes a single job with optional LangChain chain or direct LLM call.
- Streams tokens via callbacks and publishes SSE-friendly events.
- Handles cancellation and hard timeouts; returns the final accumulated text.
"""
# llm_runner.py
import asyncio
from logging import getLogger
from typing import Callable, Awaitable, Optional, Any
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately

from chat_worker.domain.ports.llm import LlmPort
from chat_worker.domain.ports.metrics_repo import MetricsRepositoryPort

from chat_worker.infrastructure.langchain.token_stream_callback import TokenStreamCallback
from chat_worker.infrastructure.langchain.metrics_callback import MetricsCallback

log = getLogger('run_llm_stream')


async def llm_runner(
        *,
        llm: LlmPort,
        job_id: str,
        user_id: str,
        messages: list[BaseMessage],
        chain: Optional[Any] = None,
        chain_input: Optional[dict] = None,
        mode: str = "gen",
        publish: Callable[[dict], Awaitable[object]],
        metrics_repo: Optional[MetricsRepositoryPort] = None,
        cancel_event: Optional[asyncio.Event] = None,
        hard_timeout_sec: Optional[float] = None,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        on_done: Optional[Callable[..., Awaitable[Any]]] = None,
        on_error: Optional[Callable[[str], Awaitable[None]]] = None,
) -> str | None:
    """
    Execute a single LLM job.
    - Runs either a LangChain `chain.ainvoke` or a direct `llm.ainvoke` with streaming callbacks.
    - Publishes per-token events ("token"), sources, usage, and heartbeat via the provided `publish` sink.
    - Guarantees a terminal "done" event even on errors/cancellation.
    - Handles cancellation and optional hard timeout.
    - Returns the final accumulated text (if any).
    """

    _nonstream_text: Optional[str] = None

    # Forward events to the primary publisher, and optionally mirror to an event sink (on_event)
    async def _publish_with_sink(event: dict):
        # Pass-through to original publish
        await publish(event)
        # Optionally forward to sink for persistence (tokens/sources/usage/heartbeat)
        if on_event is not None:
            ev_type = event.get("event") or event.get("type")
            if ev_type in {"token", "sources", "usage", "heartbeat"}:
                await on_event(ev_type, event)

    # Stream tokens and aggregate a final text from allowed tags (e.g., "final_answer")
    token_stream_cb = TokenStreamCallback(job_id=job_id, user_id=user_id, publish=_publish_with_sink,allowed_tags={"final_answer"},
                                          aggregate_final=True)

    # Persist metrics/rows via repository when available (no-op if None)
    async def _persist_row(row: dict) -> None:
        if metrics_repo is not None:
            await metrics_repo.upsert_job(row)

    # Approximate token counter for MetricsCallback (uses LangChain utility)
    token_len = lambda s: count_tokens_approximately([s])
    # Collect per-run metrics (timings, token counts) and persist via provided hook
    metric_cb = MetricsCallback(
        job_id=job_id,
        mode=mode,
        persist=_persist_row,
        token_len=token_len,
        allowed_tags={"final_answer"},
    )

    # Invoke either the provided chain or the raw LLM with streaming callbacks attached
    async def _invoke():
        # Configure callbacks for streaming tokens and metrics
        config = RunnableConfig(callbacks=[token_stream_cb, metric_cb], tags=["final_answer"])
        if chain is not None:
            prompt_value = await chain.ainvoke(chain_input or {})
            # Execute asynchronously and stream through callbacks
            await llm.astream(prompt_value.to_messages(), config)
        else:
            # Execute asynchronously and stream through callbacks
            await llm.astream(messages, config)

    async def _guarded_invoke():
        """
        Run `_invoke` under a guard loop that observes cancel_event and emits terminal events on errors.
        """
        # Spawn the invocation task
        task = asyncio.create_task(_invoke())
        try:
            while True:
                done, _pending = await asyncio.wait({task}, timeout=0.1, return_when=asyncio.FIRST_COMPLETED)
                if task in done:
                    # Completed normally
                    await task
                    return
                # Check external cancellation signal
                if cancel_event and cancel_event.is_set():
                    task.cancel()
                    raise asyncio.CancelledError("cancel_event set")
        except asyncio.CancelledError:
            # On cancellation, emit error and terminal done event
            await publish({
                "event": "error",
                "jobId": job_id,
                "code": "CANCELLED",
                "message": "Job was cancelled",
                "retryable": False,
            })
            if on_error is not None:
                await on_error("CANCELLED")
            await publish({"event": "done", "jobId": job_id})
        except Exception as e:
            # Safety net: emit error/done for any uncaught exception
            await publish({
                "event": "error",
                "jobId": job_id,
                "code": "UNCAUGHT",
                "message": str(e),
                "retryable": False,
            })
            if on_error is not None:
                await on_error(str(e))
            await publish({"event": "done", "jobId": job_id})

    if hard_timeout_sec and hard_timeout_sec > 0:
        # Enforce a hard timeout for the entire run
        try:
            await asyncio.wait_for(_guarded_invoke(), timeout=hard_timeout_sec)
            # Retrieve final aggregated text (if any) from the token stream callback
            final = token_stream_cb.final_text() or _nonstream_text
            if on_done is not None and final is not None:
                await on_done(final)
            return final
        except asyncio.TimeoutError:
            # Timeout occurred — emit error and terminal done, then return best-effort final text
            await publish({
                "event": "error",
                "jobId": job_id,
                "code": "TIMEOUT",
                "message": f"LLM run exceeded {hard_timeout_sec}s",
                "retryable": True,
            })
            if on_error is not None:
                await on_error(f"TIMEOUT:{hard_timeout_sec}")
            await publish({"event": "done", "jobId": job_id})
            # Retrieve final aggregated text (if any) from the token stream callback
            final = token_stream_cb.final_text() or _nonstream_text
            if on_done is not None and final is not None:
                await on_done(final)
            return final
    else:
        await _guarded_invoke()
        # Retrieve final aggregated text (if any) from the token stream callback
        final = token_stream_cb.final_text() or _nonstream_text
        if on_done is not None and final is not None:
            await on_done(final)
        return final
