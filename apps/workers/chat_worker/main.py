"""
Chat Worker Entrypoint
- Consumes `chat.request` from Kafka and streams model output via Redis Streams (SSE-friendly).
- Supports two modes: GEN (history-aware chat) and RAG (retrieval augmented generation via Weaviate).
- Coordinates LLM calls, history service, and per-job repository sinks. Graceful shutdown on SIGINT/SIGTERM.
"""
# main.py
import asyncio, os, signal
import json
import logging
import sys
import time
from logging import getLogger

from langchain_openai import OpenAIEmbeddings

from chat_worker.application.dto.requests import ChatRequest, TitleRequest
from chat_worker.application.rag_chain import RagPipeline
from chat_worker.application.services.chat_history_service import ChatHistoryService
from chat_worker.application.services.chat_llm_service import ChatLLMService
from chat_worker.application.services.chat_title_service import ChatTitleService
from chat_worker.infrastructure.db.pool_factory import create_pg_pool
from chat_worker.infrastructure.langchain.vllm_client import get_llm as get_vllm_llm
from chat_worker.infrastructure.langchain.weaviate_client import get_client
from chat_worker.infrastructure.repo.postgres_chat_repo import PostgresChatRepo
from chat_worker.infrastructure.repo.postgres_history_repo import PostgresHistoryRepository
from chat_worker.infrastructure.repo.postgres_metrics_repo import PostgresMetricsRepo
from chat_worker.infrastructure.repo.postgres_session_repo import PostgresChatSessionRepo
from chat_worker.settings import Settings

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

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
CHAT_REQ_TOPIC = "chat.request"
TITLE_REQ_TOPIC= "chat.title.generate"
RES_PREFIX = "chat.response."

shutdown_event = asyncio.Event()  # 👈 shutdown signal
CHAT_SEM = asyncio.Semaphore(64)  # concurrency cap per worker process
TITLE_SEM = asyncio.Semaphore(512)


async def main():
    """
    Main async loop.
    - Initializes Kafka consumer/producer, Redis client, and Postgres-backed repos.
    - Builds LLM, RAG pipeline (if enabled), and stream service.
    - Processes each request with `llm_runner` and publishes streaming events.
    """
    # Configure Kafka consumer for the chat request topic
    consumer = AIOKafkaConsumer(
        CHAT_REQ_TOPIC, TITLE_REQ_TOPIC,
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
    if pool is None:
        raise RuntimeError("Postgres connection pool initialization failed: pool is None")
    metrics_repo = PostgresMetricsRepo(pool)
    chat_repo = PostgresChatRepo(pool)
    history_repo = PostgresHistoryRepository(pool)
    session_repo = PostgresChatSessionRepo(pool)
    llm_client = await get_vllm_llm() # await get_openai_llm()

    # Warm-up/health probe (optional)
    r = await redis.info()
    # Stream publisher used to emit SSE-friendly events
    stream_service = StreamService(redis)

    async def xadd_session_event(key: str, event: dict):
        fields = {"data": json.dumps(event), "ts": str(int(time.time() * 1000))}
        await redis.xadd(key, fields, maxlen=10000, approximate=True)
        await redis.expire(key, 60)

    # History service builds context windows (system + recent turns)
    system_prompt = "You are Talkie, an assistant that answers briefly."

    weaviate_client = await get_client()
    embeddings = OpenAIEmbeddings(model=settings.EMBEDDING_MODEL)
    pipeline = RagPipeline(
        settings=settings.RAG,  # ← inject sub-config explicitly
        client=weaviate_client,     # (optional) v4 client
        embeddings=embeddings,      # (optional) embeddings
        text_key="text"
    )
    rag_chain = pipeline.build()  # 🔁 build once; reuse per request

    history_service = ChatHistoryService(history_repo, system_prompt, settings.MAX_CTX_TOKENS)
    title_service = ChatTitleService(session_repo, llm_client, xadd_session_event)
    llm_service = ChatLLMService(settings, history_service, stream_service, chat_repo, metrics_repo, rag_chain, llm_client, llm_runner)
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

            if msg.topic == CHAT_REQ_TOPIC:
                # Parse inbound Kafka message into typed request
                try:
                    value = msg.value
                    if value is None:
                        log.error("❌ Received Kafka message with empty value: key=%s, topic=%s, partition=%s, offset=%s",
                                  msg.key, msg.topic, msg.partition, msg.offset)
                        continue
                    req = ChatRequest.model_validate_json(value.decode())
                except Exception as e:
                    print(f"❌ bad payload: {e}")
                    continue

                async def _run_chat(chat_req: ChatRequest):
                    async with CHAT_SEM:
                        await llm_service.generate_response(chat_req)

                asyncio.create_task(_run_chat(req))

            elif msg.topic == TITLE_REQ_TOPIC:
                try:
                    value = msg.value
                    if value is None:
                        log.error(
                            "❌ Received Kafka message with empty value")
                        continue
                    req = TitleRequest.model_validate_json(value.decode())
                except Exception as e:
                    print(f"❌ bad payload: {e}")
                    continue
                async def _run_title(title_req: TitleRequest):
                    async with TITLE_SEM:
                        await title_service.generate_title(title_req)

                asyncio.create_task(_run_title(req))

    finally:
        if not shutdown_event.is_set():
            await shutdown()


# Run the worker
if __name__ == "__main__":
    asyncio.run(main())
