# apps/workers/chat_worker/infra/db/pool_factory.py
import asyncpg


async def create_pg_pool(dsn: str | None, min_size: int = 1, max_size: int = 10):
    if dsn is None:
        raise RuntimeError("DSN iis missing in environment variables")
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        statement_cache_size=0,
    )
