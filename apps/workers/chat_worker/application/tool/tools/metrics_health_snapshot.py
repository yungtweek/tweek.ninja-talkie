from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from chat_worker.application.tool.base import BaseTool, get_dep
from chat_worker.application.tool.types import ToolContext, ToolResult, ToolSpec, ToolError


class MetricsHealthArgs(BaseModel):
    range: Literal["15m", "1h", "6h", "24h", "7d"] = "1h"
    use_rag: Optional[bool] = None
    model_name: Optional[str] = None
    request_tag: Optional[str] = None


class MetricsHealthSnapshotTool(BaseTool[MetricsHealthArgs, dict[str, Any]]):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="metrics.health_snapshot",
            description="Summarize llm_metrics health for a time range (counts, latency percentiles, token stats).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "range": {"type": "string", "enum": ["15m", "1h", "6h", "24h", "7d"], "default": "1h"},
                    "use_rag": {"type": ["boolean", "null"]},
                    "model_name": {"type": ["string", "null"]},
                    "request_tag": {"type": ["string", "null"]},
                },
                "required": ["range"],
                "additionalProperties": False,
            },
            tags=("metrics",),
            risk="read",
        )

    async def run(self, ctx: ToolContext, args: MetricsHealthArgs) -> ToolResult[dict[str, Any]]:
        # deps에서 db/pool 꺼내오기 (예: asyncpg.Pool)
        pool = get_dep(ctx, "pg_pool")

        interval = self._to_interval(args.range)

        # WHERE 조건 동적 구성
        where = ["created_at >= now() - ($1::interval)"]
        params: list[Any] = [interval]
        i = 2

        if args.use_rag is not None:
            where.append(f"use_rag = ${i}")
            params.append(args.use_rag)
            i += 1

        if args.model_name:
            where.append(f"model_name = ${i}")
            params.append(args.model_name)
            i += 1

        if args.request_tag:
            where.append(f"request_tag = ${i}")
            params.append(args.request_tag)
            i += 1

        where_sql = " AND ".join(where)

        sql = f"""
        SELECT
          count(*)                                                AS total,
          count(*) FILTER (WHERE response_status = 0)            AS ok,
          count(*) FILTER (WHERE response_status <> 0)           AS error,

          percentile_cont(0.50) WITHIN GROUP (ORDER BY total_ms) AS p50_total_ms,
          percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) AS p95_total_ms,
          percentile_cont(0.99) WITHIN GROUP (ORDER BY total_ms) AS p99_total_ms,

          percentile_cont(0.50) WITHIN GROUP (ORDER BY ttft_ms)  AS p50_ttft_ms,
          percentile_cont(0.95) WITHIN GROUP (ORDER BY ttft_ms)  AS p95_ttft_ms,
          percentile_cont(0.99) WITHIN GROUP (ORDER BY ttft_ms)  AS p99_ttft_ms,

          avg(prompt_tokens)                                     AS avg_prompt_tokens,
          avg(completion_tokens)                                 AS avg_completion_tokens,
          avg(total_tokens)                                      AS avg_total_tokens,

          avg(gen_time_ms)                                       AS avg_gen_time_ms,
          avg(tok_per_sec)                                       AS avg_tok_per_sec,

          avg(queue_ms)                                          AS avg_queue_ms,
          avg(rag_ms)                                            AS avg_rag_ms
        FROM llm_metrics
        WHERE {where_sql}
        ;
        """

        try:
            row = await pool.fetchrow(sql, *params)
        except Exception as e:
            return ToolResult(
                ok=False,
                error=ToolError(
                    code="metrics_query_failed",
                    message=str(e),
                    details={"tool": self.spec.name},
                ),
            )

        data = dict(row) if row else {}
        return ToolResult(
            ok=True,
            data={
                "range": args.range,
                "filters": {
                    "use_rag": args.use_rag,
                    "model_name": args.model_name,
                    "request_tag": args.request_tag,
                },
                "summary": data,
            },
            meta={"trace_id": ctx.trace_id},
        )

    def _to_interval(self, r: str) -> str:
        return {
            "15m": "15 minutes",
            "1h": "1 hour",
            "6h": "6 hours",
            "24h": "24 hours",
            "7d": "7 days",
        }[r]