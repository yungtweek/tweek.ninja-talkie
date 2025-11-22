"""
PostgresHistoryRepository (asyncpg)
- Async implementation that satisfies domain/ports/history.HistoryRepository
- Uses asyncpg.Pool with `async with pool.acquire()` pattern.

Schema (expected):
  chat_sessions(
      id UUID PRIMARY KEY,
      user_id TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  chat_messages(
      id BIGSERIAL PRIMARY KEY,
      session_id UUID NOT NULL,
      role TEXT NOT NULL,         -- 'system' | 'user' | 'assistant'
      content TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  chat_summaries(
      user_id TEXT NOT NULL,
      session_id UUID NOT NULL,
      summary TEXT NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, session_id)
  );
"""
from __future__ import annotations

from typing import Literal, Sequence, List
import time
from datetime import timezone

import asyncpg

from chat_worker.domain.ports.history_repo import HistoryRepository, Turn, Role


def _to_epoch(dt) -> float:
    if dt is None:
        return time.time()
    # asyncpg returns tz-aware datetimes for TIMESTAMPTZ
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc).timestamp()
    return dt.timestamp()


class PostgresHistoryRepository(HistoryRepository):
    """
    Async repository for chat history, backed by Postgres (asyncpg).
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # --- Reading ---

    async def load(self, user_id: str, session_id: str, limit: int) -> Sequence[Turn]:
        """
        Return last `limit` turns ordered ascending by created_at,
        optionally prefixed with a summary if it exists.
        """
        turns: Sequence[Turn] = []

        # TODO
        # (optional) summary prefix — enable later if you store summaries
        # summary = await self._get_summary(user_id, session_id)
        # if summary is not None:
        #     turns.append({
        #         "role": "system",
        #         "content": f"[HISTORY SUMMARY]\n{summary['summary']}",
        #         "created_at": _to_epoch(summary["updated_at"]),
        #     })

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.role, m.content, m.created_at
                FROM chat_messages m
                JOIN chat_sessions s ON s.id = m.session_id
                WHERE s.user_id = $1 AND m.session_id = $2
                ORDER BY m.created_at DESC
                LIMIT $3;
                """,
                user_id,
                session_id,
                max(0, int(limit)),
            )

        # If the most recent row is a user message, drop it to avoid duplicating with current user_input
        if rows and str(rows[0]["role"]) == "user":
            rows = rows[1:]

        # We fetched DESC; return ASC for model friendliness
        for r in reversed(rows):
            db_role = str(r["role"])
            if db_role == "user":
                role: Role = "user"
            elif db_role == "assistant":
                role = "assistant"
            else:
                role = "system"

            item: Turn = {
                "role": role,
                "content": str(r["content"]),
                "created_at": _to_epoch(r["created_at"]),
            }
            turns.append(item)
        return turns

    async def load_all(self, user_id: str, session_id: str) -> Sequence[Turn]:
        """
        Return all turns (ASC), optionally prefixed with summary.
        """
        turns: List[Turn] = []

        # TODO
        # summary = await self._get_summary(user_id, session_id)
        # if summary is not None:
        #     turns.append({
        #         "role": "system",
        #         "content": f"[HISTORY SUMMARY]\n{summary['summary']}",
        #         "created_at": _to_epoch(summary["updated_at"]),
        #     })

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.role, m.content, m.created_at
                FROM chat_messages m
                JOIN chat_sessions s ON s.id = m.session_id
                WHERE s.user_id = $1 AND m.session_id = $2
                ORDER BY m.created_at
                """,
                user_id,
                session_id,
            )

        # If the most recent row is a user message, drop it to avoid duplicating with current user_input
        if rows and str(rows[0]["role"]) == "user":
            rows = rows[1:]


        for r in rows:
            db_role = str(r["role"])
            if db_role == "user":
                role: Role = "user"
            elif db_role == "assistant":
                role = "assistant"
            else:
                role = "system"

            item: Turn = {
                "role": role,
                "content": str(r["content"]),
                "created_at": _to_epoch(r["created_at"]),
            }
            turns.append(item)
        return turns

        # return await super().append(user_id, session_id, role, content)

    # TODO
    async def append(self, user_id: str, session_id: str, role: Literal['system'] | Literal['user'] | Literal['assistant'], content: str) -> None:
        return None
        # return await super().append(user_id, session_id, role, content)


    # --- Summary management (optional) ---

    # TODO
    async def replace_summary(self, user_id: str, session_id: str, summary: str) -> None:
        """
        Upsert chat summary for (user_id, session_id).
        """
        # async with self.pool.acquire() as conn:
        #     async with conn.transaction():
        #         await conn.execute(
        #             """
        #             INSERT INTO chat_summaries(user_id, session_id, summary)
        #             VALUES ($1, $2, $3)
        #             ON CONFLICT (user_id, session_id)
        #             DO UPDATE SET
        #                 summary = EXCLUDED.summary,
        #                 updated_at = now()
        #             """,
        #             user_id,
        #             session_id,
        #             summary,
        #         )

    # --- Internals (optional) ---

    # async def _get_summary(self, user_id: str, session_id: str):
        # async with self.pool.acquire() as conn:
        #     row = await conn.fetchrow(
        #         """
        #         SELECT summary, updated_at
        #         FROM chat_summaries
        #         WHERE user_id = $1 AND session_id = $2
        #         """,
        #         user_id,
        #         session_id,
        #     )
        #     return row