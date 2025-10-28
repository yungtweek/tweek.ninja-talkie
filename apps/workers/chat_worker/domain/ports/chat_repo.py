# apps/workers/chat_worker/domain/ports/chat_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional, Tuple


class ChatRepositoryPort(ABC):
    """Repository port for worker-side chat persistence.

    Responsibilities (DB-first design):
      - Append streaming events (token/sources/usage/done/error) to `chat_events` (append-only)
      - Finalize an assistant message on `done` with idempotent upsert using `job_id`
      - (Optional) Update job status for observability
    """

    # -------------------------
    # Event logging (append-only)
    # -------------------------
    @abstractmethod
    async def append_event(
            self,
            *,
            job_id: str,
            session_id: str,
            event_type: str,
            seq: int,
            payload: Mapping[str, Any],
    ) -> None:
        """Append a streaming event to `chat_events` with UNIQUE(job_id, seq).
        Should be idempotent: on conflict, ignore.
        """
        ...

    # -------------------------
    # Finalize assistant message (idempotent upsert)
    # -------------------------
    @abstractmethod
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
        """Persist the final assistant message for a job.

        Args:
            session_id: Chat session identifier.
            mode: 'gen' or 'rag', defines generation mode stored in chat_messages.mode.
            job_id: Worker job identifier.
            content: Final message content.
            sources: Optional source metadata.
            usage_prompt: Optional prompt token count.
            usage_completion: Optional completion token count.
            trace_id: Optional trace identifier.

        Implementation requirements:
          - Open a transaction.
          - `SELECT id FROM chat_sessions WHERE id=$1 FOR UPDATE` to serialize within the session
          - Compute `next_index = COALESCE(MAX(message_index),0)+1` for the session
          - Compute `current_turn = COALESCE(MAX(turn),0)` for the session (assistant shares the latest user turn)
          - INSERT into `chat_messages` with role='assistant', mode=mode, message_index=next_index, turn=current_turn, status='done'
          - ON CONFLICT (job_id) DO UPDATE SET content/sources/usage/status/trace_id/mode
          - RETURN (message_id, message_index, turn)
        """
        ...

    # -------------------------
    # Job status (optional but useful for recovery/monitoring)
    # -------------------------
    @abstractmethod
    async def update_job_status(
            self,
            *,
            job_id: str,
            status: str,
            error: Optional[str] = None,
    ) -> None:
        """Update `jobs.status` and `error` if needed."""
        ...
