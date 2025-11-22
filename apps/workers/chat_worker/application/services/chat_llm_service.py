from __future__ import annotations

from typing import Any, Awaitable, Callable

from chat_worker.application.dto.requests import ChatRequest
from chat_worker.application.repo_sink import RepoSink
from chat_worker.application.utils.to_langchain_messages import to_langchain_messages
from chat_worker.domain.ports.chat_repo import ChatRepositoryPort
from chat_worker.domain.ports.llm import LlmPort
from chat_worker.domain.ports.metrics_repo import MetricsRepositoryPort
from chat_worker.settings import Settings


class ChatLLMService:
    """
    ChatLLMService
    --------------
    High-level application service that orchestrates a single chat LLM request.

    Responsibilities:
    - Build inputs for GEN / RAG chat modes
    - Call the shared llm_runner with the correct parameters
    - Wire history, stream publishing, and persistence callbacks

    Low-level concerns such as Kafka consumption, Redis connection
    management, and process-level lifecycle are handled by the worker
    orchestration (main.py).
    """
    SYSTEM_PROMPT = "You are Talkie, an assistant that answers briefly."

    def __init__(
            self,
            settings: Settings,
            history_service: Any,
            stream_service: Any,
            chat_repo: ChatRepositoryPort,
            metrics_repo: MetricsRepositoryPort,
            rag_chain: Any,
            llm_client: LlmPort,
            llm_runner: Callable[..., Awaitable[None]],
    ) -> None:
        """
        Construct a ChatLLMService.

        All dependencies are injected so this service can be easily tested
        and reused from different worker entrypoints.
        """
        self._settings = settings
        self._history_service = history_service
        self._stream_service = stream_service
        self._chat_repo = chat_repo
        self._metrics_repo = metrics_repo
        self._rag_chain = rag_chain
        self._llm_client = llm_client
        self._llm_runner = llm_runner

    async def generate_response(self, req: ChatRequest) -> None:
        """
        Generate an LLM response for a single chat request.

        This method is intended to be called from the Kafka/Redis consumer
        loop, typically wrapped in `asyncio.create_task(...)` so multiple
        chat jobs can run concurrently. Concurrency should be bounded by
        the caller (e.g., using an asyncio.Semaphore in the worker loop).
        """
        mode = req.mode
        job_id = req.job_id
        user_id = req.user_id
        session_id = req.session_id
        # Build event publisher bound to (job_id, user_id)
        publish = self._stream_service.make_job_publisher(job_id, user_id)

        # Per-request sink for DB side-effects (status/metrics)
        sink = RepoSink(chat_repo=self._chat_repo, job_id=job_id, session_id=session_id, mode=mode)
        # Mark job as started (for dashboards/observability)
        await sink.on_event(
            event_type="started",
            data={"mode": mode},
        )

        # Prepare unified inputs for llm_runner
        chain = None
        chain_input = None
        messages = None
        run_mode = "gen"

        if mode == "rag":
            # RAG: use prebuilt chain, no manual messages
            rag_cfg = {
                "topK": self._settings.RAG.top_k,
                "mmq": self._settings.RAG.mmq,
                # "filters": {...}  # optional filters can be injected
            }
            chain = self._rag_chain
            chain_input = {"question": req.message, "rag": rag_cfg}
            run_mode = "rag"

        else:
            # Build history-aware message list from recent turns
            turns = await self._history_service.handle(user_id=user_id, session_id=session_id)
            messages = to_langchain_messages(self.SYSTEM_PROMPT, turns, req.message)

        # Execute unified runner (streams tokens, collects metrics, guarantees terminal events)
        await self._llm_runner(
            llm=self._llm_client,  # kept for signature compatibility
            chain=chain,  # None for GEN, chain for RAG
            chain_input=chain_input,  # None for GEN
            mode=run_mode,  # "gen" or "rag" (metrics label)
            job_id=job_id,
            user_id=user_id,
            publish=publish,
            messages=messages or [],  # [] for RAG
            metrics_repo=self._metrics_repo,
            on_event=sink.on_event,
            on_done=sink.on_done,
            on_error=sink.on_error,
        )
