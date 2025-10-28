# apps/workers/chat_worker/infra/db/pool_factory.py
import asyncpg


async def create_pg_pool(dsn: str, min_size: int = 1, max_size: int = 10):
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        statement_cache_size=0,
    )
