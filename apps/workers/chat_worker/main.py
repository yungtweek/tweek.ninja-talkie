"""
Chat Worker Entrypoint
- Consumes `chat.request` from Kafka and streams model output via Redis Streams (SSE-friendly).
- Supports two modes: GEN (history-aware chat) and RAG (retrieval augmented generation via Weaviate).
- Coordinates LLM calls, history service, and per-job repository sinks. Graceful shutdown on SIGINT/SIGTERM.
"""
# main.py
import asyncio, os, signal
import logging
import sys
from logging import getLogger
from typing import Literal

from langchain_openai import OpenAIEmbeddings

from chat_worker.application.rag_chain import RagPipeline
from chat_worker.application.repo_sink import RepoSink
from chat_worker.application.services.chat_history_service import HistoryService
from chat_worker.application.utils.to_langchain_messages import to_langchain_messages
from chat_worker.infrastructure.db.pool_factory import create_pg_pool
from chat_worker.infrastructure.langchain.openai_client import get_llm
from chat_worker.infrastructure.langchain.weaviate_client import get_client
from chat_worker.infrastructure.repo.postgres_chat_repo import PostgresChatRepo
from chat_worker.infrastructure.repo.postgres_history_repo import PostgresHistoryRepository
from chat_worker.infrastructure.repo.postgres_metrics_repo import PostgresMetricsRepo
from chat_worker.settings import Settings

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from redis.asyncio import Redis

from chat_worker.application.llm_runner import llm_runner
from chat_worker.infrastructure.stream.stream_service import StreamService

settings = Settings()

log = getLogger('ChatWorker')

LOG_LEVEL = settings.LOG_LEVEL
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Tone down noisy third‑party loggers
for noisy in ("aiokafka", "urllib3", "asyncio", "botocore", "httpcore", "httpx", "s3transfer", "boto3", "openai._base_client"):
    logging.getLogger(noisy).setLevel(settings.NOISY_LEVEL)

if settings.OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY

BOOTSTRAP = settings.KAFKA_BOOTSTRAP
REDIS_URL = settings.REDIS_URL
REQ_TOPIC = "chat.request"
RES_PREFIX = "chat.response."

shutdown_event = asyncio.Event()  # 👈 shutdown signal
SEM = asyncio.Semaphore(64)  # concurrency cap per worker process


class MyBaseModel(BaseModel):
    """
    Base Pydantic model configured for camelCase I/O (populate_by_name + alias_generator).
    """
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )


class ChatRequest(MyBaseModel):
    """
    Kafka payload shape for `chat.request`.
    """
    job_id: str
    user_id: str
    session_id: str
    message: str
    mode: Literal["gen", "rag"] = "gen"


async def main():
    """
    Main async loop.
    - Initializes Kafka consumer/producer, Redis client, and Postgres-backed repos.
    - Builds LLM, RAG pipeline (if enabled), and stream service.
    - Processes each request with `llm_runner` and publishes streaming events.
    """
    # Configure Kafka consumer for the chat request topic
    consumer = AIOKafkaConsumer(
        REQ_TOPIC,
        bootstrap_servers=BOOTSTRAP,
        group_id="chat-workers",
        retry_backoff_ms=500,
        enable_auto_commit=True,
        auto_offset_reset="earliest"
    )
    # Kafka producer (reserved for future use; present for symmetry)
    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    # Shared Redis client used by the stream service
    redis = Redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

    # Postgres pool for chat, history, and metrics repos
    pool = await create_pg_pool(settings.DB_URL)

    # Repository and model clients
    metrics_repo = PostgresMetricsRepo(pool)
    chat_repo = PostgresChatRepo(pool)
    history_repo = PostgresHistoryRepository(pool)
    llm = await get_llm()

    # Warm-up/health probe (optional)
    r = await redis.info()
    # Stream publisher used to emit SSE-friendly events
    stream_service = StreamService(redis)
    # History service builds context windows (system + recent turns)
    system_prompt = "You are Talkie, an assistant that answers briefly."
    history_service = HistoryService(history_repo, system_prompt, settings.MAX_CTX_TOKENS, settings.MAX_HISTORY_TURNS)
    weaviate_client = await get_client()
    embeddings = OpenAIEmbeddings()
    pipeline = RagPipeline(
        settings=settings.RAG,  # ← inject sub-config explicitly
        llm=llm,                    # ← reuse a single LLM instance per worker
        client=weaviate_client,     # (optional) v4 client
        embeddings=embeddings,      # (optional) embeddings
        text_key="text"
    )
    rag_chain = pipeline.build()  # 🔁 build once; reuse per request

    await consumer.start()
    await producer.start()
    print("🏁 Worker started. Press Ctrl+C to stop.")

    async def shutdown():
        print("\n🧹 Shutting down gracefully...")
        shutdown_event.set()
        await consumer.stop()
        await producer.stop()
        await redis.aclose()
        await pool.close()
        print("✅ Worker stopped cleanly.")

    # 🛑 Register SIGINT/SIGTERM handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
            # Parse inbound Kafka message into typed request
            try:
                req = ChatRequest.model_validate_json(msg.value.decode())
            except Exception as e:
                print(f"❌ bad payload: {e}")
                continue

            log.info(req)
            mode = req.mode
            job_id = req.job_id
            user_id = req.user_id
            session_id = req.session_id
            # Build event publisher bound to (job_id, user_id)
            publish = stream_service.make_job_publisher(job_id, user_id)

            # Concurrency guard: limit in-flight jobs per process
            async with SEM:
                # Per-request sink for DB side-effects (status/metrics)
                sink = RepoSink(chat_repo=chat_repo, job_id=job_id, session_id=session_id, mode=mode)
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
                        "topK": settings.RAG.top_k,
                        "mmq": settings.RAG.mmq,
                        # "filters": {...}  # optional filters can be injected
                    }
                    chain = rag_chain
                    log.info(f"rag_cfg: {rag_cfg}")
                    chain_input = {"question": req.message, "rag": rag_cfg}
                    run_mode = "rag"

                else:
                    # Build history-aware message list from recent turns
                    turns = await history_service.handle(user_id=user_id, session_id=session_id)
                    messages = to_langchain_messages(system_prompt, turns, req.message)

                # Execute unified runner (streams tokens, collects metrics, guarantees terminal events)
                await llm_runner(
                    llm=llm,                          # kept for signature compatibility
                    chain=chain,                      # None for GEN, chain for RAG
                    chain_input=chain_input,          # None for GEN
                    mode=run_mode,                    # "gen" or "rag" (metrics label)
                    job_id=job_id,
                    user_id=user_id,
                    publish=publish,
                    messages=messages or [],          # [] for RAG
                    metrics_repo=metrics_repo,
                    on_event=sink.on_event,
                    on_done=sink.on_done,
                    on_error=sink.on_error,
                )
                # log.info(f"final_text: {final_text}")

    finally:
        if not shutdown_event.is_set():
            await shutdown()


# Run the worker
if __name__ == "__main__":
    asyncio.run(main())
