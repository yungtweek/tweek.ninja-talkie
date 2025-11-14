"""
Stream Service
- Thin helper around Redis Streams for chat SSE.
- Publishes job-scoped events (token/final/done/error/ping) and provides key helpers.
- Uses approximate trimming for bounded stream size.
"""
from __future__ import annotations

import asyncio
import json
from logging import getLogger
import time
from dataclasses import dataclass
from typing import AsyncIterator, Iterable, Literal, Optional, Any, Dict, Callable, Awaitable, cast

from redis.asyncio import Redis

logger = getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Config & Key helpers
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StreamConfig:
    """
    Configuration for Redis Stream behavior.
    - block_ms: XREAD/XREADGROUP block timeout in milliseconds (short to allow idle/timeout checks).
    - maxlen_approx: MAXLEN ~N for XADD (approximate trimming for performance).
    - idle_ping_sec: Suggested SSE ping interval (router uses this value; provided here for convenience).
    - hard_timeout_sec: Suggested hard timeout for a single stream session.
    """
    # Block timeout (ms) for XREAD; keep short so the outer loop can check idle/timeout
    block_ms: int = 200
    # XADD trimming length (approximate): MAXLEN ~N
    maxlen_approx: int = 1000
    # Suggested SSE ping / timeout hints (used by routers, exposed here)
    idle_ping_sec: float = 15.0
    # Suggested hard timeout for end-to-end stream
    hard_timeout_sec: float = 120.0


def job_key(job_id: str) -> str:
    """Return the Redis hash key for job state (informational; this module focuses on events)."""
    return f"job:{job_id}"


def stream_key(job_id: str, user_id: str) -> str:
    """Return the Redis Stream key for chat events scoped by job and user."""
    return f"sse:chat:{job_id}:{user_id}:events"


# Event type alias shared by publishers and low-level helpers
EventType = Literal["meta", "token", "done", "error", "ping", "final"]


# ──────────────────────────────────────────────────────────────────────────────
# StreamService
# ──────────────────────────────────────────────────────────────────────────────
class StreamService:
    """
    - Relies on externally managed Redis lifecycle (router/worker). This class only uses the injected client(s).
    - You may inject separate clients for general commands and blocking reads.
    """

    def __init__(
            self,
            redis: Redis,
            *,
            blocking_redis: Optional[Redis] = None,
            cfg: StreamConfig = StreamConfig(),
    ):
        if redis is None:
            raise ValueError("redis client must be provided")
        self.redis = redis
        self.blocking_redis = blocking_redis or redis
        self.cfg = cfg

    def make_job_publisher(
            self,
            job_id: str,
            user_id: str,
            *,
            cfg: StreamConfig = StreamConfig(),
    ) -> Callable[[Dict[str, Any]], Awaitable[str]]:
        """
        Create a coroutine `publish(evt)` for a specific (job_id, user_id).

        Accepted events: {"meta", "token", "done", "error", "ping", "final"}

        Example payloads (the key is `event`; other keys become `data`):
            {"event": "token", "index": 0, "text": "He"}
            {"event": "final", "content": "..."}
            {"event": "error", "code": "E_CONN", "message": "...", "retryable": false}
            {"event": "done", "finish_reason": "stop", "usage": {...}}

        Notes:
        - On `done`, the stream key is set to expire in ~60s (cleanup).
        - Internally calls `_xadd(redis, job_id, user_id, event, data)` with JSON-serialized data.
        """
        allowed: set[EventType] = {"meta", "token", "done", "error", "ping", "final"}

        async def publish(evt: Dict[str, Any]) -> str:
            # Expect an 'event' key; everything else goes into 'data'
            evt_type = evt.get("event")
            # Guard against unsupported event types
            if not evt_type or not isinstance(evt_type, str):
                raise ValueError("publish(evt): missing or invalid 'type'")
            if evt_type not in allowed:
                raise ValueError(f"publish(evt): unsupported type '{evt_type}'")
            # Fast-expire the stream shortly after completion
            if evt_type == "done":
                await self.redis.expire(stream_key(job_id, user_id), 60)
            # Exclude routing fields from the serialized payload
            data = {k: v for k, v in evt.items() if k not in ("type", "job_id", "user_id")}
            evt_typed = cast(EventType, evt_type)
            return await self._xadd(
                self.redis,
                job_id,
                user_id,
                evt_typed,
                data,
                maxlen_approx=cfg.maxlen_approx,
            )

        return publish

    @staticmethod
    async def _xadd(
            redis: Redis,
            job_id: str,
            user_id: str,
            event: EventType,
            data: dict,
            *,
            maxlen_approx: int,
            add_ts: bool = True,
    ) -> str:
        """Append an entry to the Redis Stream with event and JSON-encoded data; return entry id."""
        # Normalize xadd fields: event + compact JSON data (+ optional timestamp)
        fields = {
            "event": event,
            "data": _json_dumps(data),
        }
        if add_ts:
            fields["ts"] = str(int(time.time() * 1000))
            
        # Use approximate trimming for performance
        sid: str = await redis.xadd(
            stream_key(job_id, user_id),
            fields, # type: ignore[arg-type]
            maxlen=maxlen_approx,
            approximate=True,
        )
        return sid

    @staticmethod
    def _parse_xread_reply(reply) -> Iterable[tuple[str, list[tuple[str, dict]]]]:
        """Normalize XREAD reply into pythonic tuples with decoded bytes."""
        if not reply:
            return []
        parsed = []
        for stream_name, entries in reply:
            name = stream_name.decode() if isinstance(stream_name, (bytes, bytearray)) else stream_name
            norm_entries = []
            for entry_id, fields in entries:
                eid = entry_id.decode() if isinstance(entry_id, (bytes, bytearray)) else entry_id
                norm_fields = {
                    (k.decode() if isinstance(k, (bytes, bytearray)) else k):
                        (v.decode() if isinstance(v, (bytes, bytearray)) else v)
                    for k, v in fields.items()
                }
                norm_entries.append((eid, norm_fields))
            parsed.append((name, norm_entries))
        return parsed


# ──────────────────────────────────────────────────────────────────────────────
# Low-level utils
# ──────────────────────────────────────────────────────────────────────────────

def _json_dumps(obj: dict) -> str:
    # Keep Unicode intact and use compact separators
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


async def safe_publish(publish: Callable[[Dict[str, Any]], Awaitable[Any]], evt: Dict[str, Any]) -> None:
    try:
        # Shield against cancellation and avoid aborting the outer loop
        await asyncio.shield(publish(evt))
    except asyncio.CancelledError:
        # During cancellation, silently skip
        return
    except RuntimeError as e:
        # Ignore when the event loop is already closed
        if "Event loop is closed" in str(e):
            return
        raise
