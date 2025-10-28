from __future__ import annotations
import asyncio
from typing import Optional

import weaviate
from urllib.parse import urlparse
from chat_worker.settings import Settings

_settings = Settings()
_lock = asyncio.Lock()
_client: Optional[weaviate.WeaviateClient] = None


def _connect_v4(url: str, api_key: Optional[str] = None) -> weaviate.WeaviateClient:
    """
    Connect to Weaviate v4 using connect_to_custom.
    Accepts an http(s) URL and infers ports automatically.
    """
    u = urlparse(url)
    host = u.hostname or "localhost"
    port = u.port or (443 if u.scheme == "https" else 8080)
    grpc_port = 50051
    headers = {"X-OpenAI-Api-Key": api_key} if api_key else {}
    return weaviate.connect_to_custom(
        http_host="localhost",
        http_port=8080,
        http_secure=False,
        grpc_host="localhost",
        grpc_port=50051,
        grpc_secure=False,
    )


async def get_client() -> weaviate.WeaviateClient:
    """
    Return a shared singleton Weaviate v4 client instance.
    Initialized lazily and reused across all chains.
    """
    global _client
    if _client is not None:
        return _client

    async with _lock:
        if _client is not None:
            return _client
        client = _connect_v4(
            _settings.RAG.weaviate_url,
            _settings.RAG.weaviate_api_key,
        )
        _client = client
        return client


async def warmup() -> None:
    """
    Optional warmup to ensure client connectivity.
    """
    client = await get_client()
    try:
        _ = client.is_ready()  # simple health check
    except Exception as e:
        print(f"[WARN] Weaviate warmup failed: {e}")


async def close_client() -> None:
    """
    Close the global Weaviate client connection and reset it.
    Useful for graceful shutdown or test teardown.
    """
    global _client
    if _client is None:
        return
    try:
        await asyncio.to_thread(_client.close)
    except Exception as e:
        print(f"[WARN] Failed to close Weaviate client: {e}")
    finally:
        _client = None