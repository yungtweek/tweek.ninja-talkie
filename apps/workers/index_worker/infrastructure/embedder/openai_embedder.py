

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from typing import Iterable, List, Sequence

import aiohttp

logger = logging.getLogger(__name__)


def _chunks(seq: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


class OpenAIEmbedder:
    """
    Async OpenAI Embeddings client (minimal, dependency-light).

    - Uses aiohttp directly (no SDK dependency)
    - Batches inputs, with exponential backoff on 429/5xx
    - Returns list[List[float]] aligned with input order
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
        batch_size: int = 128,
        timeout_s: int = 60,
        max_retries: int = 5,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required")

        self.model = model
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com").rstrip("/")
        self.batch_size = max(1, batch_size)
        self.timeout_s = timeout_s
        self.max_retries = max_retries

        self._endpoint = f"{self.base_url}/v1/embeddings"
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def embed_batch(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not texts:
            return []

        results: List[List[float]] = []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_s)) as sess:
            for chunk in _chunks(list(texts), self.batch_size):
                vecs = await self._embed_once(sess, list(chunk))
                results.extend(vecs)
        return results

    async def _embed_once(self, sess: aiohttp.ClientSession, inputs: List[str]) -> List[List[float]]:
        payload = {"model": self.model, "input": inputs}

        for attempt in range(self.max_retries):
            try:
                async with sess.post(self._endpoint, data=json.dumps(payload), headers=self._headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # expected: { data: [ { embedding: [...] }, ... ] }
                        out = [item["embedding"] for item in data.get("data", [])]
                        if len(out) != len(inputs):
                            raise RuntimeError(
                                f"embedding size mismatch: got {len(out)} for {len(inputs)} inputs"
                            )
                        return out

                    # retryable
                    if resp.status in (429, 500, 502, 503, 504):
                        text = await resp.text()
                        wait = self._backoff(attempt)
                        logger.warning(
                            "embed retryable status %s (attempt %s/%s): %s",
                            resp.status,
                            attempt + 1,
                            self.max_retries,
                            text[:300],
                        )
                        await asyncio.sleep(wait)
                        continue

                    # non-retryable
                    text = await resp.text()
                    raise RuntimeError(f"openai embeddings error {resp.status}: {text[:500]}")

            except aiohttp.ClientError as ce:
                # network error → retry
                wait = self._backoff(attempt)
                logger.warning("embed network error (attempt %s/%s): %s", attempt + 1, self.max_retries, ce)
                await asyncio.sleep(wait)
                continue

        raise RuntimeError("openai embeddings: max retries exceeded")

    @staticmethod
    def _backoff(attempt: int) -> float:
        base = 0.5 * (2 ** attempt)
        jitter = random.uniform(0, 0.25)
        return min(10.0, base + jitter)