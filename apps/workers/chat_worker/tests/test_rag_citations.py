import unittest
from typing import Any, List

from langchain_core.messages import HumanMessage

from chat_worker.application.llm_runner import llm_runner
from chat_worker.application.repo_sink import RepoSink, _extract_citations
from chat_worker.application.rag.document import Document
from chat_worker.application.rag_chain import RagPipeline
from chat_worker.config.rag import RagConfig


class DummyEmbeddings:
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        return [0.0, 0.0, 0.0]


class DummyPrompt:
    def to_messages(self) -> list[HumanMessage]:
        return [HumanMessage(content="test")]


class DummyChain:
    async def ainvoke(self, _inputs: dict) -> dict:
        return {"prompt": DummyPrompt(), "citations": [{"id": "S1"}]}


class DummyLlm:
    provider = "test"
    model = "test"

    async def astream(self, _messages: list, _config: Any = None, tools: Any = None) -> None:
        return None


class RagCitationTests(unittest.TestCase):
    def test_join_context_builds_citations(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        docs = [
            Document(
                title="Doc1",
                page_content="alpha",
                chunk_id="c1",
                page=1,
                uri="https://example.com/1",
                metadata={"rerank_score": 0.9},
            ),
            Document(
                title="Doc2",
                page_content="beta",
                chunk_id="c2",
                page=2,
            ),
        ]

        context, citations = pipeline.join_context(docs)

        self.assertIn("[Doc1]", context)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["source_id"], "S1")
        self.assertEqual(citations[0]["chunk_id"], "c1")
        self.assertEqual(citations[0]["page"], 1)
        self.assertEqual(citations[0]["uri"], "https://example.com/1")
        self.assertEqual(citations[0]["rerank_score"], 0.9)
        self.assertEqual(citations[0]["score"], 0.9)

    def test_join_context_respects_budget(self) -> None:
        rag_cfg = RagConfig(max_context=4)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        docs = [
            Document(title="Doc1", page_content="abcd", chunk_id="c1"),
            Document(title="Doc2", page_content="efgh", chunk_id="c2"),
        ]

        _context, citations = pipeline.join_context(docs)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["chunk_id"], "c1")


class LlmRunnerSourcesEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_runner_emits_sources_event(self) -> None:
        published: list[dict] = []
        mirrored: list[str] = []

        async def publish(evt: dict) -> None:
            published.append(evt)

        async def on_event(event_type: str, _data: dict) -> None:
            mirrored.append(event_type)

        await llm_runner(
            llm=DummyLlm(),
            job_id="job-1",
            user_id="user-1",
            messages=[],
            chain=DummyChain(),
            chain_input={"question": "q"},
            publish=publish,
            on_event=on_event,
            on_done=None,
            on_error=None,
        )

        self.assertTrue(any(evt.get("event") == "sources" for evt in published))
        self.assertIn("sources", mirrored)


class RagStageEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_rag_stage_events_emitted(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        docs = [Document(title="Doc1", page_content="alpha", chunk_id="c1")]

        class DummyRerankCfg:
            top_n = 3
            max_candidates = 10
            batch_size = 5
            max_doc_chars = 250

        class DummyReranker:
            _cfg = DummyRerankCfg()

            def rerank(self, _query: str, items: list[Document]) -> list[Document]:
                return items

        pipeline.reranker = DummyReranker()

        class DummyRetriever:
            def invoke(self, _q: str, **_kwargs) -> list[Document]:
                return docs

        pipeline.build_retriever = lambda **_kwargs: DummyRetriever()  # type: ignore[assignment]

        published: list[dict] = []
        recorded: list[str] = []

        async def publish(evt: dict) -> None:
            published.append(evt)

        async def record_event(event_type: str, _payload: dict) -> None:
            recorded.append(event_type)

        chain = pipeline.build()
        await chain.ainvoke(
            {
                "question": "hello",
                "rag": {},
                "stream": {
                    "publish": publish,
                    "record_event": record_event,
                    "job_id": "job-1",
                    "user_id": "user-1",
                    "session_id": "sess-1",
                },
            }
        )

        expected = {
            "rag_retrieve.in_progress",
            "rag_retrieve.completed",
            "rag_rerank.in_progress",
            "rag_rerank.completed",
            "rag_mmr.in_progress",
            "rag_mmr.completed",
            "rag_compress.in_progress",
            "rag_compress.completed",
        }
        emitted = {evt.get("event") for evt in published}
        for name in expected:
            self.assertIn(name, emitted)
            self.assertIn(name, recorded)

        rerank_done = next(evt for evt in published if evt.get("event") == "rag_rerank.completed")
        self.assertIn("inputHits", rerank_done)
        self.assertIn("outputHits", rerank_done)
        self.assertEqual(rerank_done.get("reranker"), "DummyReranker")
        self.assertEqual(rerank_done.get("rerankTopN"), 3)

        mmr_done = next(evt for evt in published if evt.get("event") == "rag_mmr.completed")
        self.assertIn("mmrK", mmr_done)
        self.assertIn("mmrFetchK", mmr_done)
        self.assertIn("mmrLambda", mmr_done)

        compress_done = next(evt for evt in published if evt.get("event") == "rag_compress.completed")
        self.assertIn("inputHits", compress_done)
        self.assertIn("outputHits", compress_done)
        self.assertIn("maxContext", compress_done)
        self.assertIn("useLlm", compress_done)
        self.assertIn("heuristicHits", compress_done)
        self.assertIn("llmApplied", compress_done)
        self.assertFalse(compress_done.get("llmApplied"))

class DummyChatRepo:
    def __init__(self) -> None:
        self.finalize_calls: list[dict] = []
        self.saved_citations: list[dict] = []
        self.job_status_updates: list[dict] = []
        self.job_events: list[dict] = []

    async def append_event(
        self,
        *,
        job_id: str,
        session_id: str,
        event_type: str,
        seq: int,
        payload: dict,
    ) -> None:
        return None

    async def append_job_event(
        self,
        *,
        job_id: str,
        user_id: str,
        session_id: str | None,
        event_type: str,
        payload: dict,
    ) -> None:
        self.job_events.append(
            {
                "job_id": job_id,
                "user_id": user_id,
                "session_id": session_id,
                "event_type": event_type,
                "payload": payload,
            }
        )

    async def finalize_assistant_message(
        self,
        *,
        session_id: str,
        mode: str = "gen",
        job_id: str,
        content: str,
        sources: dict | None = None,
        usage_prompt: int | None = None,
        usage_completion: int | None = None,
        trace_id: str | None = None,
    ) -> tuple[str, int, int]:
        self.finalize_calls.append(
            {
                "session_id": session_id,
                "mode": mode,
                "job_id": job_id,
                "content": content,
                "sources": sources,
                "usage_prompt": usage_prompt,
                "usage_completion": usage_completion,
                "trace_id": trace_id,
            }
        )
        return "msg-1", 1, 1

    async def save_message_citations(
        self,
        *,
        message_id: str,
        session_id: str,
        citations: list[dict],
    ) -> None:
        self.saved_citations.append(
            {
                "message_id": message_id,
                "session_id": session_id,
                "citations": citations,
            }
        )

    async def update_job_status(
        self,
        *,
        job_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        self.job_status_updates.append(
            {"job_id": job_id, "status": status, "error": error}
        )


class RepoSinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_on_done_persists_citations(self) -> None:
        repo = DummyChatRepo()
        sink = RepoSink(
            chat_repo=repo,
            job_id="job-1",
            user_id="user-1",
            session_id="sess-1",
            mode="rag",
        )
        citations = [{"source_id": "S1", "file_name": "Doc1", "chunk_id": "c1"}]

        msg_id, idx, turn = await sink.on_done(
            "final",
            sources={"citations": citations},
            usage_prompt=10,
            usage_completion=20,
        )

        self.assertEqual((msg_id, idx, turn), ("msg-1", 1, 1))
        self.assertEqual(len(repo.finalize_calls), 1)
        self.assertEqual(repo.finalize_calls[0]["sources"], {"citations": citations})
        self.assertEqual(len(repo.saved_citations), 1)
        self.assertEqual(repo.saved_citations[0]["citations"], citations)
        self.assertEqual(repo.job_status_updates[-1]["status"], "done")

    async def test_on_done_skips_missing_citations(self) -> None:
        repo = DummyChatRepo()
        sink = RepoSink(
            chat_repo=repo,
            job_id="job-2",
            user_id="user-2",
            session_id="sess-2",
        )

        await sink.on_done("final", sources={"foo": "bar"})

        self.assertEqual(len(repo.saved_citations), 0)
        self.assertEqual(repo.job_status_updates[-1]["status"], "done")

    async def test_on_job_event_persists(self) -> None:
        repo = DummyChatRepo()
        sink = RepoSink(
            chat_repo=repo,
            job_id="job-3",
            user_id="user-3",
            session_id="sess-3",
        )

        await sink.on_job_event(
            "rag_retrieve.completed",
            {"query": "hi", "hits": 2, "tookMs": 10},
        )

        self.assertEqual(len(repo.job_events), 1)
        self.assertEqual(repo.job_events[0]["job_id"], "job-3")
        self.assertEqual(repo.job_events[0]["user_id"], "user-3")
        self.assertEqual(repo.job_events[0]["session_id"], "sess-3")
        self.assertEqual(repo.job_events[0]["event_type"], "rag_retrieve.completed")
        self.assertEqual(repo.job_events[0]["payload"]["hits"], 2)

    async def test_on_event_persists_done_only(self) -> None:
        repo = DummyChatRepo()
        sink = RepoSink(
            chat_repo=repo,
            job_id="job-4",
            user_id="user-4",
            session_id="sess-4",
        )

        await sink.on_event("token", {"event": "token", "content": "hi"})
        await sink.on_event("done", {"event": "done", "jobId": "job-4", "foo": "bar"})

        self.assertEqual(len(repo.job_events), 1)
        self.assertEqual(repo.job_events[0]["event_type"], "done")
        self.assertEqual(repo.job_events[0]["payload"], {"foo": "bar"})

    async def test_on_event_persists_tool_calls(self) -> None:
        repo = DummyChatRepo()
        sink = RepoSink(
            chat_repo=repo,
            job_id="job-5",
            user_id="user-5",
            session_id="sess-5",
        )

        await sink.on_event(
            "tool.call.in_progress",
            {"event": "tool.call.in_progress", "jobId": "job-5", "tool": "ping", "argsPreview": "{}"},
        )
        await sink.on_event(
            "tool.call.completed",
            {"event": "tool.call.completed", "jobId": "job-5", "tool": "ping", "resultPreview": "ok"},
        )

        self.assertEqual(len(repo.job_events), 2)
        self.assertEqual(repo.job_events[0]["event_type"], "tool.call.in_progress")
        self.assertEqual(repo.job_events[0]["payload"]["tool"], "ping")
        self.assertEqual(repo.job_events[1]["event_type"], "tool.call.completed")
        self.assertEqual(repo.job_events[1]["payload"]["resultPreview"], "ok")

    def test_extract_citations_handles_collections(self) -> None:
        citations = [{"source_id": "S1"}]
        self.assertEqual(_extract_citations(citations), citations)
        self.assertEqual(
            _extract_citations({"citations": citations + ["bad"]}),
            citations,
        )
        self.assertEqual(_extract_citations({"sources": citations}), citations)
