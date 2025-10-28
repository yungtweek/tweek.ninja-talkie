# apps/workers/index_worker/infrastructure/di.py
import asyncpg

from index_worker.domain.ports import Embedder, VectorRepository, MetadataRepo
from index_worker.infrastructure.embedder.openai_embedder import OpenAIEmbedder
from index_worker.infrastructure.vectors.weaviate_repo import WeaviateVectorRepository
from index_worker.infrastructure.persistence.pg_metadata_repo import PgMetadataRepo
from index_worker.settings import Settings


async def make_embedder(settings: Settings) -> Embedder:
    return OpenAIEmbedder(api_key=settings.OPENAI_API_KEY, model=settings.EMBEDDING_MODEL)

async def make_vector_repo(settings: Settings) -> VectorRepository:
    return WeaviateVectorRepository(
        url=settings.WEAVIATE_URL,
        api_key=settings.WEAVIATE_API_KEY,
        collection=settings.WEAVIATE_COLLECTION,
        batch_size=settings.BATCH_SIZE,
    )

async def shutdown_vector_repo(repo: VectorRepository):
    await repo.close()

async def make_metadata_repo(settings: Settings) -> MetadataRepo:
    pool = await asyncpg.create_pool(dsn=settings.DATABASE_URL)
    return PgMetadataRepo(pool)

async def shutdown_metadata_repo(repo: MetadataRepo):
    pool = getattr(repo, "pool", None)
    if pool:
        await pool.close()