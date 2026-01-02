import json
import os
import re
import unittest
from pathlib import Path

from chat_worker.application.rag.postprocessors.reranker import LLMReranker, RerankConfig

BASE_DIR = Path(__file__).resolve().parents[1]

def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and value[0] in {"'", '"'} and value[-1:] == value[:1]:
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def _load_env_files() -> None:
    for name in (".env", ".env.local"):
        _load_dotenv(BASE_DIR / name)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _rerank_config() -> RerankConfig:
    _load_env_files()
    prefix = "RERANK__"
    return RerankConfig(
        max_candidates=_env_int(f"{prefix}MAX_CANDIDATES", 30),
        top_n=_env_int(f"{prefix}TOP_N", 0),
        batch_size=_env_int(f"{prefix}BATCH_SIZE", 10),
        max_doc_chars=_env_int(f"{prefix}MAX_DOC_CHARS", 1800),
        temperature=_env_float(f"{prefix}TEMPERATURE", 0.0),
        max_output_tokens=_env_int(f"{prefix}MAX_OUTPUT_TOKENS", 600),
        fail_open=_env_bool(f"{prefix}FAIL_OPEN", True),
    )


class DummyDoc:
    def __init__(self, page_content: str, metadata):
        self.page_content = page_content
        self.metadata = metadata


class DummyReranker(LLMReranker):
    def _call_llm(self, prompt: str, cfg: RerankConfig, *, job_id: str | None = None) -> str:
        ids = re.findall(r"id=([^\n]+)", prompt)
        results = [
            {"id": rid, "score": 1.0 - i * 0.1, "reason": "ok"} for i, rid in enumerate(ids)
        ]
        return json.dumps(results)


class RerankerTests(unittest.TestCase):
    def test_rerank_handles_duplicate_ids(self):
        docs = [
            DummyDoc("alpha", {"chunk_id": "dup"}),
            DummyDoc("beta", {"chunk_id": "dup"}),
        ]
        cfg = _rerank_config()
        reranker = DummyReranker(llm=object(), config=cfg)
        out = reranker.rerank("query", docs)

        expected_len = len(docs) if cfg.top_n <= 0 else min(len(docs), cfg.top_n)
        self.assertEqual(len(out), expected_len)
        scores = [doc.metadata.get("rerank_score") for doc in docs]
        self.assertEqual(len(set(scores)), 2)

    def test_rerank_normalizes_metadata(self):
        docs = [
            DummyDoc("alpha", None),
            DummyDoc("beta", "not-a-dict"),
        ]
        cfg = _rerank_config()
        reranker = DummyReranker(llm=object(), config=cfg)
        out = reranker.rerank("query", docs)

        expected_len = len(docs) if cfg.top_n <= 0 else min(len(docs), cfg.top_n)
        self.assertEqual(len(out), expected_len)
        for doc in docs:
            self.assertIsInstance(doc.metadata, dict)
            self.assertIn("rerank_score", doc.metadata)


if __name__ == "__main__":
    unittest.main()
