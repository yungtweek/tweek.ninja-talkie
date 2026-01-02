import inspect
from logging import getLogger
from typing import Any, Sequence

from langchain_core.embeddings import Embeddings

from chat_worker.application.rag.compressors.heuristic import HeuristicCompressor
from chat_worker.application.rag.compressors.llm import LLMContextualCompressor
from chat_worker.application.rag.document import Document

logger = getLogger("RagPipeline")

def _supports_kwarg(func: Any, name: str) -> bool:
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    if name in sig.parameters:
        return True
    return any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )

def _has_rerank_score(docs: Sequence[Document]) -> bool:
    for d in docs:
        md = getattr(d, "metadata", None)
        if isinstance(md, dict) and md.get("rerank_score") is not None:
            return True
    return False


def _total_chars(docs: Sequence[Document]) -> int:
    total = 0
    for d in docs:
        total += len(getattr(d, "page_content", "") or "")
    return total


def _should_apply_llm(
    docs: Sequence[Document],
    *,
    max_context: int | None,
) -> bool:
    if not docs or len(docs) < 2:
        return False
    if max_context is None or max_context <= 0:
        return False
    if not _has_rerank_score(docs):
        return False
    return _total_chars(docs) >= max_context * 0.7

async def compress_docs(
    docs: Sequence[Document],
    query: str,
    *,
    embeddings: Embeddings,
    max_context: int | None,
    llm_compressor: LLMContextualCompressor | Any | None = None,
    use_llm: bool = False,
    job_id: str | None = None,
) -> tuple[list[Document], int, bool]:
    compressor = HeuristicCompressor(embeddings=embeddings, max_context=max_context)
    heuristic_docs = compressor.compress_docs(query=query, docs=docs)
    heuristic_hits = len(heuristic_docs)

    if not use_llm or llm_compressor is None:
        return heuristic_docs, heuristic_hits, False
    if not _should_apply_llm(heuristic_docs, max_context=max_context):
        return heuristic_docs, heuristic_hits, False

    try:
        if hasattr(llm_compressor, "acompress_docs"):
            compress_call = llm_compressor.acompress_docs
            if job_id is not None and _supports_kwarg(compress_call, "job_id"):
                out = await compress_call(
                    query=query,
                    docs=heuristic_docs,
                    job_id=job_id,
                )
            else:
                out = await compress_call(
                    query=query,
                    docs=heuristic_docs,
                )
        else:
            compress_call = llm_compressor.compress_docs
            if job_id is not None and _supports_kwarg(compress_call, "job_id"):
                out = compress_call(
                    query=query,
                    docs=heuristic_docs,
                    job_id=job_id,
                )
            else:
                out = compress_call(
                    query=query,
                    docs=heuristic_docs,
                )
    except Exception as e:
        logger.warning("[RAG][compress][llm] failed: %s", e)
        return heuristic_docs, heuristic_hits, False

    if out:
        return list(out), heuristic_hits, True
    return heuristic_docs, heuristic_hits, False
