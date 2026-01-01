"""
LLM Runner (Chat Worker)
- Executes a single job with optional LangChain chain or direct LLM call.
- Streams tokens via callbacks and publishes SSE-friendly events.
- Handles cancellation and hard timeouts; returns the final accumulated text.
"""
# llm_runner.py
import asyncio
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from time import monotonic, time
from logging import getLogger
from typing import Callable, Awaitable, Optional, Any, Mapping, Sequence
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

from chat_worker.domain.ports.llm import LlmPort
from chat_worker.domain.ports.metrics_repo import MetricsRepositoryPort

from chat_worker.infrastructure.langchain.token_stream_callback import TokenStreamCallback
from chat_worker.infrastructure.langchain.metrics_callback import MetricsCallback
from chat_worker.application.rag_chain import RagState
from chat_worker.application.tool.registry import specs_to_openai_tools
from chat_worker.application.tool.types import ToolCall, ToolContext, ToolResult, ToolSpec

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
        queue_ms: Optional[int] = None,
        outbox_published_at: Optional[datetime] = None,
        cancel_event: Optional[asyncio.Event] = None,
        hard_timeout_sec: Optional[float] = None,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        on_done: Optional[Callable[..., Awaitable[Any]]] = None,
        on_error: Optional[Callable[[str], Awaitable[None]]] = None,
        tool_dispatcher: Optional[Any] = None,
        tool_specs: Optional[Sequence[ToolSpec]] = None,
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
    sources_payload: Optional[dict] = None
    final_text: Optional[str] = None
    publish_done_manually = False
    invoke_failed = False
    tool_defs: Optional[list[Mapping[str, Any]]] = None
    tool_name_map: dict[str, str] = {}

    def _sanitize_tool_name(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", name)

    def _sanitize_tool_specs(
            specs: Sequence[ToolSpec],
    ) -> tuple[list[ToolSpec], dict[str, str]]:
        sanitized: list[ToolSpec] = []
        name_map: dict[str, str] = {}
        used: set[str] = set()
        for spec in specs:
            base = _sanitize_tool_name(spec.name)
            safe = base
            suffix = 1
            while safe in used:
                safe = f"{base}_{suffix}"
                suffix += 1
            used.add(safe)
            if safe != spec.name:
                name_map[safe] = spec.name
            sanitized.append(
                ToolSpec(
                    name=safe,
                    description=spec.description,
                    parameters_schema=spec.parameters_schema,
                    tags=spec.tags,
                    risk=spec.risk,
                    result_schema=spec.result_schema,
                )
            )
        return sanitized, name_map

    if tool_dispatcher is not None and tool_specs:
        sanitized_specs, tool_name_map = _sanitize_tool_specs(tool_specs)
        tool_defs = specs_to_openai_tools(sanitized_specs)

    # Forward events to the primary publisher, and optionally mirror to an event sink (on_event)
    async def _publish_with_sink(event: dict):
        # Pass-through to original publish
        await publish(event)
        # Optionally forward to sink for persistence (tokens/sources/usage/heartbeat/done/final)
        if on_event is not None:
            ev_type = event.get("event") or event.get("type")
            if ev_type in {
                "token",
                "sources",
                "usage",
                "heartbeat",
                "done",
                "final",
                "tool.call.in_progress",
                "tool.call.completed",
            }:
                await on_event(ev_type, event)

    # Stream tokens and aggregate a final text from allowed tags (e.g., "final_answer")
    token_stream_cb = TokenStreamCallback(
        job_id=job_id,
        user_id=user_id,
        publish=_publish_with_sink,
        allowed_tags={"final_answer"},
        aggregate_final=True,
    )

    # Persist metrics/rows via repository when available (no-op if None)
    async def _persist_row(row: dict) -> None:
        if metrics_repo is not None:
            await metrics_repo.upsert_job(row)

    # Approximate token counter for MetricsCallback (uses LangChain utility)
    token_len = lambda s: count_tokens_approximately([s])
    first_token_delta_ms = None
    if metrics_repo is not None and outbox_published_at is not None:
        async def _first_token_delta_ms() -> int | None:
            offset_ms = await metrics_repo.db_time_offset_ms()
            if offset_ms is None:
                return None
            now_wall_ms = int(time() * 1000)
            first_token_db_ms = now_wall_ms + offset_ms
            published_ms = int(outbox_published_at.timestamp() * 1000)
            return max(0, first_token_db_ms - published_ms)
        first_token_delta_ms = _first_token_delta_ms

    # Collect per-run metrics (timings, token counts) and persist via provided hook
    metric_cb = MetricsCallback(
        job_id=job_id,
        mode=mode,
        provider=llm.provider,
        model=llm.model,
        persist=_persist_row,
        token_len=token_len,
        allowed_tags=None,
        queue_ms=queue_ms,
        first_token_delta_ms=first_token_delta_ms,
    )

    def _extract_tool_calls(message: BaseMessage) -> list[Any]:
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            return list(tool_calls)
        additional = getattr(message, "additional_kwargs", None) or {}
        return list(additional.get("tool_calls") or [])

    def _coerce_tool_args(args: Any) -> Mapping[str, Any]:
        if args is None:
            return {}
        if isinstance(args, Mapping):
            return args
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
                if isinstance(parsed, Mapping):
                    return parsed
                return {"_raw": parsed}
            except json.JSONDecodeError:
                return {"_raw": args}
        return {"_raw": args}

    def _get_field(obj: Any, key: str) -> Any:
        if isinstance(obj, Mapping):
            return obj.get(key)
        return getattr(obj, key, None)

    def _normalize_tool_calls(
            raw_calls: Sequence[Any],
            name_map: Optional[Mapping[str, str]] = None,
    ) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for raw in raw_calls or []:
            name = _get_field(raw, "name")
            args = _get_field(raw, "args") or _get_field(raw, "arguments")
            call_id = _get_field(raw, "id") or _get_field(raw, "call_id") or _get_field(raw, "tool_call_id")

            function = _get_field(raw, "function")
            if name is None and function is not None:
                name = _get_field(function, "name")
            if args is None and function is not None:
                args = _get_field(function, "arguments") or _get_field(function, "args")

            if not name:
                continue
            if name_map and name in name_map:
                name = name_map[name]

            calls.append(
                ToolCall(
                    name=str(name),
                    arguments=_coerce_tool_args(args),
                    call_id=str(call_id) if call_id is not None else None,
                )
            )
        return calls

    def _json_default(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, timedelta):
            return value.total_seconds()
        if isinstance(value, Enum):
            return value.value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "dict"):
            return value.dict()
        if isinstance(value, set):
            return list(value)
        return str(value)

    def _tool_result_to_content(result: ToolResult[Any]) -> str:
        payload: dict[str, Any] = {"ok": result.ok}
        if result.ok:
            payload["data"] = result.data
        else:
            payload["error"] = {
                "code": result.error.code if result.error else "tool_error",
                "message": result.error.message if result.error else "Tool failed",
                "details": result.error.details if result.error else None,
            }
        if result.meta:
            payload["meta"] = dict(result.meta)
        return json.dumps(payload, ensure_ascii=True, default=_json_default)

    def _preview_payload(value: Any, max_len: int = 500) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            preview = value
        else:
            try:
                preview = json.dumps(value, ensure_ascii=True, default=_json_default)
            except TypeError:
                preview = str(value)
        if len(preview) > max_len:
            return f"{preview[: max_len - 3]}..."
        return preview

    class ToolCallCaptureCallback(AsyncCallbackHandler):
        def __init__(self) -> None:
            self.message: Optional[BaseMessage] = None
            self.raw_tool_calls: list[Any] = []

        async def on_llm_end(self, response: Any, **_kwargs: Any) -> None:
            try:
                generations = getattr(response, "generations", None) or []
                if not generations or not generations[0]:
                    return
                gen0 = generations[0][0]
                message = getattr(gen0, "message", None)
                if message is None:
                    return
                self.message = message
                self.raw_tool_calls = _extract_tool_calls(message)
            except Exception:
                return

        async def on_chat_model_end(self, response: Any, **kwargs: Any) -> None:
            await self.on_llm_end(response, **kwargs)

    # Invoke either the provided chain or the raw LLM with streaming callbacks attached
    async def _invoke():
        nonlocal sources_payload, _nonstream_text, final_text, publish_done_manually
        if chain is not None:
            # Configure callbacks for streaming tokens and metrics
            config = RunnableConfig(callbacks=[token_stream_cb, metric_cb], tags=["final_answer"])
            rag_started_at = monotonic()
            result = await chain.ainvoke(chain_input or {})
            metric_cb.set_rag_ms(int((monotonic() - rag_started_at) * 1000))
            if isinstance(result, RagState):
                prompt_value = result.prompt
                if prompt_value is None:
                    raise ValueError("RAG chain returned RagState without prompt")
                citations = result.citations
                if citations is not None:
                    sources_payload = {"citations": citations}
                    await _publish_with_sink(
                        {
                            "event": "sources",
                            "jobId": job_id,
                            "userId": user_id,
                            **sources_payload,
                        }
                    )
            elif isinstance(result, dict) and "prompt" in result:
                prompt_value = result["prompt"]
                citations = result.get("citations")
                if citations is not None:
                    sources_payload = {"citations": citations}
                    await _publish_with_sink(
                        {
                            "event": "sources",
                            "jobId": job_id,
                            "userId": user_id,
                            **sources_payload,
                        }
                    )
            else:
                prompt_value = result
            # Execute asynchronously and stream through callbacks
            await llm.astream(prompt_value.to_messages(), config)
            final_text = token_stream_cb.final_text() or _nonstream_text
            return

        if tool_dispatcher is None:
            # Configure callbacks for streaming tokens and metrics
            config = RunnableConfig(callbacks=[token_stream_cb, metric_cb], tags=["final_answer"])
            # Execute asynchronously and stream through callbacks
            log.debug("no tool dispatcher, running LLM directly")
            await llm.astream(messages, config)
            final_text = token_stream_cb.final_text() or _nonstream_text
            return

        publish_done_manually = True
        tool_deps: dict[str, Any] = {}
        if metrics_repo is not None and hasattr(metrics_repo, "pool"):
            tool_deps["pg_pool"] = getattr(metrics_repo, "pool")

        tool_ctx = ToolContext(
            trace_id=job_id,
            now_iso=datetime.now(timezone.utc).isoformat(),
            deps=tool_deps,
            user_id=user_id,
        )

        current_messages = list(messages)
        max_rounds = 3
        round_index = 0

        while True:
            tool_capture_cb = ToolCallCaptureCallback()
            token_stream_cb_round = TokenStreamCallback(
                job_id=job_id,
                user_id=user_id,
                publish=_publish_with_sink,
                allowed_tags={"final_answer"},
                aggregate_final=True,
                emit_done=False,
                suppress_tool_calls=True,
            )
            config = RunnableConfig(
                callbacks=[token_stream_cb_round, metric_cb, tool_capture_cb],
                tags=["final_answer"],
            )
            log.debug(f"tool:  {tool_defs}")
            await llm.astream(current_messages, config, tools=tool_defs)
            final_text = token_stream_cb_round.final_text() or _nonstream_text

            raw_calls = tool_capture_cb.raw_tool_calls
            tool_calls = _normalize_tool_calls(raw_calls, tool_name_map)
            if tool_calls:
                log.info(
                    "tool calls requested",
                    extra={
                        "job_id": job_id,
                        "round": round_index,
                        "tool_count": len(tool_calls),
                        "tools": [call.name for call in tool_calls],
                    },
                )
            else:
                log.debug(
                    "no tool calls requested",
                    extra={"job_id": job_id, "round": round_index},
                )
            if not tool_calls:
                break

            if tool_capture_cb.message is not None:
                current_messages.append(tool_capture_cb.message)

            for idx, call in enumerate(tool_calls):
                tool_call_id = call.call_id or f"{call.name}:{idx}"
                args_preview = _preview_payload(call.arguments)
                await _publish_with_sink(
                    {
                        "event": "tool.call.in_progress",
                        "jobId": job_id,
                        "userId": user_id,
                        "tool": call.name,
                        "callId": tool_call_id,
                        "attempt": round_index + 1,
                        "tookMs": None,
                        "argsPreview": args_preview,
                        "resultPreview": None,
                    }
                )
                started_at = monotonic()
                result = await tool_dispatcher.dispatch(tool_ctx, call)
                took_ms = int((monotonic() - started_at) * 1000)
                log.info(
                    "tool call result",
                    extra={
                        "job_id": job_id,
                        "round": round_index,
                        "tool": call.name,
                        "ok": result.ok,
                        "error": result.error.code if result.error else None,
                    },
                )
                content = _tool_result_to_content(result)
                await _publish_with_sink(
                    {
                        "event": "tool.call.completed",
                        "jobId": job_id,
                        "userId": user_id,
                        "tool": call.name,
                        "callId": tool_call_id,
                        "attempt": round_index + 1,
                        "tookMs": took_ms,
                        "argsPreview": args_preview,
                        "resultPreview": _preview_payload(content),
                    }
                )
                current_messages.append(
                    ToolMessage(content=content, tool_call_id=tool_call_id)
                )

            round_index += 1
            if round_index >= max_rounds:
                log.warning("tool loop max rounds reached", extra={"job_id": job_id})
                break

    async def _guarded_invoke():
        """
        Run `_invoke` under a guard loop that observes cancel_event and emits terminal events on errors.
        """
        nonlocal invoke_failed
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
            invoke_failed = True
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
            invoke_failed = True

    if hard_timeout_sec and hard_timeout_sec > 0:
        # Enforce a hard timeout for the entire run
        try:
            await asyncio.wait_for(_guarded_invoke(), timeout=hard_timeout_sec)
            # Retrieve final aggregated text (if any) from the token stream callback
            final = final_text or token_stream_cb.final_text() or _nonstream_text
            if publish_done_manually and not invoke_failed:
                await _publish_with_sink({"event": "done", "jobId": job_id, "userId": user_id})
            if on_done is not None and final is not None:
                if sources_payload is not None:
                    await on_done(final, sources=sources_payload)
                else:
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
            final = final_text or token_stream_cb.final_text() or _nonstream_text
            if on_done is not None and final is not None:
                if sources_payload is not None:
                    await on_done(final, sources=sources_payload)
                else:
                    await on_done(final)
            return final
    else:
        await _guarded_invoke()
        # Retrieve final aggregated text (if any) from the token stream callback
        final = final_text or token_stream_cb.final_text() or _nonstream_text
        if publish_done_manually and not invoke_failed:
            await _publish_with_sink({"event": "done", "jobId": job_id, "userId": user_id})
        if on_done is not None and final is not None:
            if sources_payload is not None:
                await on_done(final, sources=sources_payload)
            else:
                await on_done(final)
        return final
