from __future__ import annotations
import asyncpg
from time import monotonic, time
from typing import Any, Mapping
from chat_worker.domain.ports.metrics_repo import MetricsRepositoryPort


class PostgresMetricsRepo(MetricsRepositoryPort):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._db_time_offset_ms: int | None = None
        self._db_time_offset_expires_at: float = 0.0
        self._db_time_offset_ttl_sec = 10.0

    async def upsert_job(self, row: Mapping[str, Any]) -> None:
        sql = """
              INSERT INTO llm_metrics (
                  request_id, trace_id, span_id, parent_span_id, span_name, user_id,
                  request_tag, provider, model_name, model_path,
                  use_rag, rag_hits, count_eot,
                  prompt_chars, prompt_tokens, output_chars, completion_tokens,
                  ttft_ms, gen_time_ms, total_ms, tok_per_sec,
                  queue_ms,
                  published_to_first_token_ms,
                  rag_ms,
                  response_status, error_message)
              VALUES ($1, $2, $3, $4, $5, $6,
                      COALESCE($7, 'unknown'), COALESCE($8, 'unknown'), $9, COALESCE($10, 'unknown'),
                      COALESCE($11, false), COALESCE($12, 0), COALESCE($13, true),
                      COALESCE($14, 0), COALESCE($15, 0), COALESCE($16, 0), COALESCE($17, 0),
                      $18, $19, $20, $21,
                      $22,
                      $23,
                      $24,
                      COALESCE($25, 0), $26) \
              """
        args = (
            row.get("request_id"),
            row.get("trace_id"),
            row.get("span_id"),
            row.get("parent_span_id"),
            row.get("span_name"),
            row.get("user_id"),
            row.get("request_tag"),
            row.get("provider"),
            row.get("model_name"),
            row.get("model_path"),
            row.get("use_rag"),
            row.get("rag_hits"),
            row.get("count_eot"),
            row.get("prompt_chars"),
            row.get("prompt_tokens"),
            row.get("output_chars"),
            row.get("completion_tokens"),
            row.get("ttft_ms"),
            row.get("gen_time_ms"),
            row.get("total_ms"),
            row.get("tok_per_sec"),
            row.get("queue_ms"),
            row.get("published_to_first_token_ms"),
            row.get("rag_ms"),
            row.get("response_status"),
            row.get("error_message"),
        )
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *args)

    async def upsert_message(self, row: Mapping[str, Any]) -> None:
        pass

    async def db_time_offset_ms(self) -> int | None:
        now = monotonic()
        if self._db_time_offset_ms is not None and now < self._db_time_offset_expires_at:
            return self._db_time_offset_ms
        sql = "SELECT clock_timestamp() AS now"
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql)
            if not row or row.get("now") is None:
                return self._db_time_offset_ms
            db_now_ms = int(row["now"].timestamp() * 1000)
            local_now_ms = int(time() * 1000)
            self._db_time_offset_ms = db_now_ms - local_now_ms
            self._db_time_offset_expires_at = now + self._db_time_offset_ttl_sec
            return self._db_time_offset_ms
        except Exception:
            return self._db_time_offset_ms
