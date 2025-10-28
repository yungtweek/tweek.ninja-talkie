# apps/workers/chat_worker/infra/repo/postgres_metrics_repo.py
from __future__ import annotations
import asyncpg
from typing import Any, Mapping
from chat_worker.domain.ports.metrics_repo import MetricsRepositoryPort


class PostgresMetricsRepo(MetricsRepositoryPort):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def upsert_job(self, row: Mapping[str, Any]) -> None:
        sql = """
              INSERT INTO llm_metrics (
                  request_id, trace_id, span_id, parent_span_id, user_id,
                  request_tag, model_name, model_path,
                  use_rag, rag_hits, count_eot,
                  prompt_chars, prompt_tokens, output_chars, completion_tokens,
                  ttft_ms, gen_time_ms, total_ms, tok_per_sec,
                  response_status, error_message)
              VALUES ($1, $2, $3, $4, $5,
                      COALESCE($6, 'unknown'), $7, COALESCE($8, 'unknown'),
                      COALESCE($9, false), COALESCE($10, 0), COALESCE($11, true),
                      COALESCE($12, 0), COALESCE($13, 0), COALESCE($14, 0), COALESCE($15, 0),
                      $16, $17, $18, $19,
                      COALESCE($20, 0), $21) \
              """
        args = (
            row.get("request_id"),
            row.get("trace_id"),
            row.get("span_id"),
            row.get("parent_span_id"),
            row.get("user_id"),
            row.get("request_tag"),
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
            row.get("response_status"),
            row.get("error_message"),
        )
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *args)

    async def upsert_message(self, row: Mapping[str, Any]) -> None:
        pass
