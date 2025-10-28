from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Tuple

import asyncpg

from chat_worker.domain.ports.chat_repo import ChatRepositoryPort


class PostgresChatRepo(ChatRepositoryPort):
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
    # Event logging (append-only)
    # -------------------------
    async def append_event(
            self,
            *,
            job_id: str,
            session_id: str,
            event_type: str,
            seq: int,
            payload: Mapping[str, Any],
    ) -> None:
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        sql = (
            """
            INSERT INTO chat_events (job_id, session_id, event_type, seq, payload_json)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (job_id, seq) DO NOTHING;
            """
        )
        async with self.pool.acquire() as conn:
            await conn.execute(sql, job_id, session_id, event_type, seq, payload_json)

    # -------------------------
    # Finalize assistant message (idempotent upsert)
    # -------------------------
    async def finalize_assistant_message(
            self,
            *,
            session_id: str,
            mode: str = "gen",
            job_id: str,
            content: str,
            sources: Optional[Mapping[str, Any]] = None,
            usage_prompt: Optional[int] = None,
            usage_completion: Optional[int] = None,
            trace_id: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        """Persist the final assistant message (with mode) for a job and return (id, message_index, turn).

        Algorithm (within a single transaction):
          1) Lock session row: SELECT id FROM chat_sessions WHERE id=$1 FOR UPDATE
          2) next_index = COALESCE(MAX(message_index),0)+1 for the session
          3) current_turn = COALESCE(MAX(turn),0) for the session (assistant shares latest user turn)
          4) INSERT ... ON CONFLICT (job_id) DO UPDATE ... RETURNING id, message_index, turn
        """
        insert_sql = (
            """
            INSERT INTO chat_messages (id, session_id, role, mode, content, message_index, turn, job_id,
                                       sources_json, usage_prompt, usage_completion, status, trace_id)
            VALUES (gen_random_uuid(), $1, 'assistant', $2, $3, $4, $5, $6,
                    $7::jsonb, $8, $9, 'done', $10)
            ON CONFLICT (job_id) DO UPDATE SET content          = EXCLUDED.content,
                                               mode             = EXCLUDED.mode,
                                               sources_json     = EXCLUDED.sources_json,
                                               usage_prompt     = EXCLUDED.usage_prompt,
                                               usage_completion = EXCLUDED.usage_completion,
                                               status           = 'done',
                                               trace_id         = COALESCE(EXCLUDED.trace_id, chat_messages.trace_id)
            RETURNING id, message_index, turn;
            """
        )

        sources_json = json.dumps(sources or {}, ensure_ascii=False)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 1) Lock the parent session to serialize index allocation
                await conn.execute(
                    "SELECT id FROM chat_sessions WHERE id=$1 FOR UPDATE;",
                    session_id,
                )

                # 2) Compute next message_index
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(MAX(message_index), 0) + 1 AS next_index
                    FROM chat_messages
                    WHERE session_id = $1;
                    """,
                    session_id,
                )
                next_index: int = int(row["next_index"]) if row else 1

                # 3) Compute current turn (assistant shares latest user turn)
                row2 = await conn.fetchrow(
                    """
                    SELECT COALESCE(MAX(turn), 0) AS current_turn
                    FROM chat_messages
                    WHERE session_id = $1;
                    """,
                    session_id,
                )
                current_turn: int = int(row2["current_turn"]) if row2 else 0

                # 4) Upsert assistant message and return identifiers
                rec = await conn.fetchrow(
                    insert_sql,
                    session_id,     # $1
                    mode,           # $2
                    content,        # $3
                    next_index,     # $4
                    current_turn,   # $5
                    job_id,         # $6
                    sources_json,   # $7
                    usage_prompt,   # $8
                    usage_completion, # $9
                    trace_id,       # $10
                )

        # asyncpg.Record -> tuple
        return str(rec["id"]), int(rec["message_index"]), int(rec["turn"])

    # -------------------------
    # Job status updates (optional)
    # -------------------------
    async def update_job_status(
            self,
            *,
            job_id: str,
            status: str,
            error: Optional[str] = None,
    ) -> None:
        sql = (
            """
            UPDATE jobs
            SET status     = $2,
                error      = $3,
                updated_at = now()
            WHERE id = $1;
            """
        )
        async with self.pool.acquire() as conn:
            await conn.execute(sql, job_id, status, error)
