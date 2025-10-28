# apps/workers/chat_worker/domain/ports/metrics_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Mapping

class MetricsRepositoryPort(ABC):
    """
    Port (contract) for persisting LLM run results and metrics.
    - Defines the minimal write surface required by the chat worker.
    - Implementations may target Postgres, SQLite, or any other store.

    Expected fields for upserts (recommendation):
    - job_id: str — correlation id for the run
    - user_id: str
    - session_id: str | None
    - message_id: str | None
    - model: str
    - prompt_tokens: int | None
    - completion_tokens: int | None
    - total_tokens: int | None
    - latency_ms: int | None
    - status: Literal['queued','running','succeeded','failed','canceled'] | str
    - error: str | None
    - created_at / updated_at: datetime | str (ISO)
    """
    @abstractmethod
    async def upsert_job(self, row: Mapping[str, Any]) -> None:
        """
        Create or update a job-level metrics row.
        - Idempotent per job_id.
        - `row` is a flat mapping validated by the concrete adapter.
        """
    @abstractmethod
    async def upsert_message(self, row: Mapping[str, Any]) -> None:
        """
        Create or update a message-level metrics row (per streamed segment or final).
        - Idempotent per message_id (or (job_id, segment_id) depending on schema).
        - `row` is a flat mapping validated by the concrete adapter.
        """
