# chat_worker/application/repo_sink.py
import asyncio
from typing import Mapping, Any, Optional
from chat_worker.domain.ports.chat_repo import ChatRepositoryPort


class RepoSink:
    def __init__(self, *, chat_repo: ChatRepositoryPort, job_id: str, session_id: str, mode: str = "gen"):
        self.chat_repo = chat_repo
        self.job_id = job_id
        self.session_id = session_id
        self.mode = mode
        self.seq = 0

    async def on_event(self, event_type: str, data: Mapping[str, Any]):
        self.seq += 1

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
