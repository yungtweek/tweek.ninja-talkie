"""
Index Worker Entrypoint
- Consumes Kafka events for ingest requests and deletions.
- Coordinates embedding, vector upsert, and metadata updates.
- Implements graceful shutdown on SIGINT/SIGTERM.
"""
# main.py
import asyncio
import json
import logging
import signal
import sys
from logging import getLogger
from typing import Any

from aiokafka import AIOKafkaConsumer
from pydantic import ConfigDict, BaseModel
from pydantic.alias_generators import to_camel

from index_worker.application.cleanup_file import cleanup_file
from index_worker.application.handlers.on_index_request import IndexRequestHandler
from index_worker.application.use_cases.index_document import IndexDocumentUseCase
from index_worker.settings import Settings

from index_worker.infrastructure.di import make_embedder, make_vector_repo, make_metadata_repo, \
    shutdown_metadata_repo, shutdown_vector_repo
from index_worker.infrastructure.objectstore.s3_client import download_file_to_bytes
from redis.asyncio import Redis

logger = getLogger('IndexWorker')

settings = Settings()
LOG_LEVEL = settings.LOG_LEVEL
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

shutdown_event = asyncio.Event()

for noisy in ("aiokafka", "urllib3", "asyncio", "botocore", "httpcore", "httpx", "s3transfer", "boto3"):
    logging.getLogger(noisy).setLevel(settings.NOISY_LEVEL)


class MyBaseModel(BaseModel):
    """
    Base Pydantic model configured for camelCase JSON I/O.
    - `alias_generator` uses `to_camel` for outgoing keys
    - `populate_by_name` allows using snake_case in code while accepting camelCase inputs
    """
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )


class IndexingRequest(MyBaseModel):
    """
    Kafka message shape for indexing requests (`ingest.request`).
    """
    job_id: str
    user_id: str
    file_id: str
    filename: str
    bucket: str
    key: str


class DeletionRequest(MyBaseModel):
    """
    Kafka message shape for deletion requests (`ingest.delete`).
    """
    job_id: str
    user_id: str
    file_id: str


# Kafka topics consumed by this worker
KAFKA_TOPIC_INGEST_REQUEST = 'ingest.request'
KAFKA_TOPIC_INGEST_DELETE = 'ingest.delete'


async def main():
    """
    Main async entrypoint.
    - Initializes Kafka consumer, repositories, and embedder.
    - Runs a message loop dispatching to indexing or deletion flows.
    - Ensures graceful shutdown of external resources.
    """
    # Configure a shared consumer for both topics in the same consumer group
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC_INGEST_REQUEST,
        KAFKA_TOPIC_INGEST_DELETE,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP,
        group_id="index-workers",
        retry_backoff_ms=500,
        enable_auto_commit=True,
        auto_offset_reset="earliest"
    )

    embedder = await make_embedder(settings)
    vector_repo = await make_vector_repo(settings)
    metadata_repo = await make_metadata_repo(settings)
    redis = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    await consumer.start()
    logger.info("🏁 Worker started. Press Ctrl+C to stop.")

    # Graceful shutdown: stop loops, close repos and Kafka client, flush logs
    async def shutdown():
        logger.info("\n🧹 Shutting down gracefully...")
        shutdown_event.set()
        await shutdown_metadata_repo(metadata_repo)
        await shutdown_vector_repo(vector_repo)
        await consumer.stop()
        logger.info("✅ Worker stopped cleanly.")

    # 🛑 Register SIGINT/SIGTERM handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: (shutdown_event.set(), asyncio.create_task(shutdown())))

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
            try:
                topic = msg.topic
                raw_json = msg.value.decode()

                if topic == KAFKA_TOPIC_INGEST_REQUEST:
                    # ---- Indexing flow -------------------------------------------------
                    # Parse and validate Kafka payload into a typed request
                    req = IndexingRequest.model_validate_json(raw_json)

                    job_id = req.job_id
                    user_id = req.user_id
                    file_id = req.file_id
                    key = req.key
                    bucket = req.bucket
                    filename = req.filename

                    # Download original file bytes from object storage (blocking I/O on a thread)
                    raw = await asyncio.to_thread(download_file_to_bytes, bucket, key)
                    if not raw:
                        await metadata_repo.mark_failed(file_id, "S3 download failed")
                        logger.error(f"[{job_id}] S3 download failed: bucket={bucket} key={key}")
                        continue

                    async def publish_file_event(event: dict[str, Any]) -> None:
                        await redis.publish(f"user:{user_id}:files", json.dumps(event))

                    # Construct use-case with shared dependencies and default chunking config
                    index_service = IndexDocumentUseCase(
                        embedder=embedder,
                        vector_repo=vector_repo,
                        metadata_repo=metadata_repo,
                        default_embedding_model=settings.EMBEDDING_MODEL,
                        default_chunk_mode="token",
                        default_chunk_size=500,
                        default_overlap=50,
                        emit_event=publish_file_event,
                    )

                    # Build application-level payload passed into the request handler
                    payload = dict(
                        user_id=user_id,
                        file_id=file_id,
                        bucket=bucket,
                        key=key,
                        raw_bytes=raw,
                        filename=filename,
                    )
                    # Run the indexing flow (extract → clean → chunk → embed → upsert)
                    await IndexRequestHandler(index_service).handle(payload=payload)

                elif topic == KAFKA_TOPIC_INGEST_DELETE:
                    # ---- Deletion flow -------------------------------------------------
                    # Parse and validate deletion request
                    req = DeletionRequest.model_validate_json(raw_json)
                    job_id = req.job_id
                    user_id = req.user_id
                    file_id = req.file_id

                    # Perform vector store + metadata cleanup (idempotent)
                    await cleanup_file(user_id,
                                       file_id,
                                       reason=KAFKA_TOPIC_INGEST_DELETE,
                                       vector_repo=vector_repo,
                                       metadata_repo=metadata_repo,
                                       job_id=job_id,
                                       logger=logger)

                else:
                    # Defensive branch: we only subscribe to known topics, but keep the guard for safety
                    # Unknown topic (shouldn't happen if we only subscribed to known topics)
                    logger.warning(f"Received message on unexpected topic: {topic}")
                    continue

            except Exception as e:
                # Log and skip malformed or unexpected messages without crashing the loop
                logger.exception(f"❌ Bad payload: {e}")
                continue



    finally:
        # Ensure resources are closed if an exception escaped the loop
        if not shutdown_event.is_set():
            await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
