# apps/workers/chat_worker/infra/repo/postgres_chat_repo.py
from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Tuple

import asyncpg

from title_worker.domain.port.session_repo import ChatSessionRepository


class PostgresChatSessionRepo(ChatSessionRepository):
    """Postgres implementation of the worker-side chat repository.

    Notes
    -----
    - DB-first design: events are append-only; a final assistant message is upserted by job_id.
    - Concurrency: lock the parent session row to serialize message_index allocation.
    - Idempotency: (job_id) unique for assistant messages, (job_id, seq) unique for events.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # -------------------------
    # Job status updates (optional)
    # -------------------------
    async def upsert_session_title(
            self,
            *,
            user_id: str,
            session_id: str,
            title: str,
    ) -> None:
        sql = (
            """
            UPDATE chat_sessions
            SET title      = $3,
                updated_at = now()
            WHERE id = $2
              AND user_id = $1;
            """
        )
        async with self.pool.acquire() as conn:
            await conn.execute(sql, user_id, session_id, title)
