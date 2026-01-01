# chat_worker/application/repo_sink.py
import asyncio
from logging import getLogger
from typing import Any, Mapping, Optional, Sequence
from chat_worker.domain.ports.chat_repo import ChatRepositoryPort


logger = getLogger("RepoSink")


class RepoSink:
    def __init__(
            self,
            *,
            chat_repo: ChatRepositoryPort,
            job_id: str,
            user_id: str,
            session_id: str,
            mode: str = "gen",
    ):
        self.chat_repo = chat_repo
        self.job_id = job_id
        self.user_id = user_id
        self.session_id = session_id
        self.mode = mode
        self.seq = 0

    async def on_event(self, event_type: str, data: Mapping[str, Any]):
        self.seq += 1
        if event_type not in {
            "done",
            "final",
            "tool.call.in_progress",
            "tool.call.completed",
        }:
            return
        payload = {
            k: v
            for k, v in (data or {}).items()
            if k not in ("event", "type", "jobId", "userId", "sessionId")
        }
        await self.chat_repo.append_job_event(
            job_id=self.job_id,
            user_id=self.user_id,
            session_id=self.session_id,
            event_type=event_type,
            payload=payload,
        )

    async def on_done(
            self,
            final_text: str,
            sources: Optional[Mapping[str, Any]] = None,
            usage_prompt: Optional[int] = None,
            usage_completion: Optional[int] = None,
    ):
        msg_id, idx, turn = await self.chat_repo.finalize_assistant_message(
            session_id=self.session_id,
            mode=self.mode,
            job_id=self.job_id,
            content=final_text,
            sources=sources,
            usage_prompt=usage_prompt,
            usage_completion=usage_completion,
        )
        citations = _extract_citations(sources)
        if citations:
            try:
                await self.chat_repo.save_message_citations(
                    message_id=msg_id,
                    session_id=self.session_id,
                    citations=citations,
                )
            except Exception as exc:
                logger.warning("Failed to save message citations: %s", exc)
        await self.chat_repo.update_job_status(job_id=self.job_id, status="done")
        return msg_id, idx, turn

    async def on_error(self, message: str):
        self.seq += 1
        await self.chat_repo.append_event(
            job_id=self.job_id,
            session_id=self.session_id,
            event_type="error",
            seq=self.seq,
            payload={"message": message},
        )
        await self.chat_repo.update_job_status(job_id=self.job_id, status="error", error=message)

    async def on_job_event(self, event_type: str, data: Mapping[str, Any]) -> None:
        await self.chat_repo.append_job_event(
            job_id=self.job_id,
            user_id=self.user_id,
            session_id=self.session_id,
            event_type=event_type,
            payload=data,
        )


def _extract_citations(sources: Optional[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]:
    if not sources:
        return []
    if isinstance(sources, list):
        return [s for s in sources if isinstance(s, Mapping)]
    for key in ("citations", "sources", "items", "docs"):
        value = sources.get(key)
        if isinstance(value, list):
            return [s for s in value if isinstance(s, Mapping)]
    return []
