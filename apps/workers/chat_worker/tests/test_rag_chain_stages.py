import unittest
from typing import Any, List

from chat_worker.application.rag.document import Document
from chat_worker.application.rag_chain import RagPipeline, RagState
from chat_worker.config.rag import RagConfig


class DummyEmbeddings:
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        return [0.0, 0.0, 0.0]


class RagChainStageTests(unittest.IsolatedAsyncioTestCase):
    def test_rag_state_helpers(self) -> None:
        state = RagState.from_inputs(
            {"question": "q", "extra": {"foo": 1}, "custom": "val"}
        )
        self.assertEqual(state.extra["foo"], 1)
        self.assertEqual(state.extra["custom"], "val")

        updated = state.copy_with(rag={"topK": 2}, extra={"bar": 3})
        self.assertEqual(updated.rag["topK"], 2)
        self.assertEqual(updated.extra["foo"], 1)
        self.assertEqual(updated.extra["bar"], 3)

        prompt_state = state.copy_with(prompt="p", citations=[{"id": "S1"}])
        self.assertEqual(prompt_state.to_prompt_result(), {"prompt": "p", "citations": [{"id": "S1"}]})

        raw = state.to_dict()
        self.assertNotIn("context", raw)
        self.assertEqual(raw["question"], "q")

    async def test_stage_retrieve_returns_docs(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        docs = [Document(title="Doc1", page_content="alpha")]

        class DummyRetriever:
            def invoke(self, _q: str, **_kwargs):
                return docs

        pipeline.build_retriever = lambda **_kwargs: DummyRetriever()  # type: ignore[assignment]

        out = await pipeline.stage_retrieve({"question": "q", "rag": {"topK": 3}})

        self.assertIsInstance(out, RagState)
        self.assertEqual(out.docs, docs)
        self.assertEqual(out.rag["topK"], 3)
        self.assertIn("has_stream", out.stream_ctx)
        self.assertFalse(out.stream_ctx["has_stream"])

    async def test_stage_retrieve_applies_mmq(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        from chat_worker.application import rag_chain as rag_chain_module

        class DummyRetriever:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def invoke(self, q: str, **_kwargs):
                self.calls.append(q)
                return [Document(title=q, page_content=q, chunk_id=q)]

        dummy = DummyRetriever()
        pipeline.build_retriever = lambda **_kwargs: dummy  # type: ignore[assignment]

        called: dict[str, int] = {}

        def fake_expand(_q: str, mmq: int) -> list[str]:
            called["mmq"] = mmq
            return ["q1", "q2"]

        original_expand = rag_chain_module.expand_queries
        rag_chain_module.expand_queries = fake_expand  # type: ignore[assignment]

        try:
            out = await pipeline.stage_retrieve({"question": "orig", "rag": {"mmq": 2}})
        finally:
            rag_chain_module.expand_queries = original_expand

        self.assertEqual(called["mmq"], 2)
        self.assertEqual(dummy.calls, ["q1", "q2"])
        self.assertEqual([doc.chunk_id for doc in out.docs], ["q1", "q2"])

    async def test_stage_mmr_uses_config_overrides(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        docs = [Document(title="Doc1", page_content="alpha", chunk_id="c1")]

        from chat_worker.application import rag_chain as rag_chain_module

        captured: dict[str, Any] = {}

        class DummyMMRPostprocessor:
            def __init__(self, cfg) -> None:
                captured["cfg"] = cfg

            def apply(self, *, query: str, docs: list[Document]):
                return docs

        original = rag_chain_module.MMRPostprocessor
        rag_chain_module.MMRPostprocessor = DummyMMRPostprocessor  # type: ignore[assignment]
        try:
            await pipeline.stage_mmr(
                {
                    "question": "q",
                    "docs": docs,
                    "rag": {
                        "mmrK": 1,
                        "mmrFetchK": 4,
                        "mmrLambda": 0.5,
                        "mmrSimilarityThreshold": None,
                    },
                }
            )
        finally:
            rag_chain_module.MMRPostprocessor = original

        cfg = captured["cfg"]
        self.assertEqual(cfg.k, 1)
        self.assertEqual(cfg.fetch_k, 4)
        self.assertEqual(cfg.lambda_mult, 0.5)
        self.assertIsNone(cfg.similarity_threshold)

    async def test_stage_rerank_applies_reranker(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        doc1 = Document(title="Doc1", page_content="alpha")
        doc2 = Document(title="Doc2", page_content="beta")

        class DummyReranker:
            def rerank(
                self,
                _query: str,
                items: list[Document],
                *,
                job_id: str | None = None,
            ) -> list[Document]:
                return list(reversed(items))

        pipeline.reranker = DummyReranker()

        out = await pipeline.stage_rerank({"question": "q", "docs": [doc1, doc2]})

        self.assertEqual(out.reranked_docs, [doc2, doc1])

    async def test_stages_skip_when_no_docs(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        called = {"rerank": False, "mmr": False, "compress": False}

        class DummyReranker:
            def rerank(
                self,
                _query: str,
                items: list[Document],
                *,
                job_id: str | None = None,
            ) -> list[Document]:
                called["rerank"] = True
                return items

        pipeline.reranker = DummyReranker()

        async def fake_compress(
            docs: List[Document],
            _query: str,
            *,
            max_context=None,
            use_llm=None,
            job_id: str | None = None,
        ):
            called["compress"] = True
            return docs, len(docs), False

        pipeline.compress_docs = fake_compress  # type: ignore[assignment]

        from chat_worker.application import rag_chain as rag_chain_module

        class DummyMMRPostprocessor:
            def __init__(self, cfg) -> None:
                called["mmr"] = True

            def apply(self, *, query: str, docs: list[Document]):
                return docs

        original = rag_chain_module.MMRPostprocessor
        rag_chain_module.MMRPostprocessor = DummyMMRPostprocessor  # type: ignore[assignment]
        try:
            rerank_out = await pipeline.stage_rerank({"question": "q", "docs": []})
            self.assertEqual(rerank_out.reranked_docs, [])

            mmr_out = await pipeline.stage_mmr(rerank_out)
            self.assertEqual(mmr_out.mmr_docs, [])

            compress_out = await pipeline.stage_compress(mmr_out)
            self.assertEqual(compress_out.compressed_docs, [])
            self.assertEqual(compress_out.heuristic_hits, 0)
            self.assertFalse(compress_out.llm_applied)
        finally:
            rag_chain_module.MMRPostprocessor = original

        self.assertFalse(called["rerank"])
        self.assertFalse(called["mmr"])
        self.assertFalse(called["compress"])

    async def test_stage_compress_returns_metadata(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        doc1 = Document(title="Doc1", page_content="alpha")
        doc2 = Document(title="Doc2", page_content="beta")

        async def fake_compress(
            docs: List[Document],
            _query: str,
            *,
            max_context=None,
            use_llm=None,
            job_id: str | None = None,
        ):
            return [docs[0]], 1, False

        pipeline.compress_docs = fake_compress  # type: ignore[assignment]

        out = await pipeline.stage_compress({"question": "q", "docs": [doc1, doc2]})

        self.assertEqual(out.compressed_docs, [doc1])
        self.assertEqual(out.heuristic_hits, 1)
        self.assertFalse(out.llm_applied)

    async def test_stage_compress_applies_max_context_override(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        doc1 = Document(title="Doc1", page_content="alpha")
        seen: dict[str, Any] = {}

        async def fake_compress(
            docs: List[Document],
            _query: str,
            *,
            max_context=None,
            use_llm=None,
            job_id: str | None = None,
        ):
            seen["max_context"] = max_context
            return docs, len(docs), False

        pipeline.compress_docs = fake_compress  # type: ignore[assignment]

        await pipeline.stage_compress({"question": "q", "docs": [doc1], "rag": {"maxContext": 42}})

        self.assertEqual(seen["max_context"], 42)

    async def test_stage_compress_applies_use_llm_override(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        doc1 = Document(title="Doc1", page_content="alpha")
        seen: dict[str, Any] = {}

        async def fake_compress(
            docs: List[Document],
            _query: str,
            *,
            max_context=None,
            use_llm=None,
            job_id: str | None = None,
        ):
            seen["use_llm"] = use_llm
            return docs, len(docs), False

        pipeline.compress_docs = fake_compress  # type: ignore[assignment]

        await pipeline.stage_compress({"question": "q", "docs": [doc1], "rag": {"useLlm": False}})

        self.assertFalse(seen["use_llm"])

    async def test_stage_join_context_falls_back_to_docs(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        doc1 = Document(title="Doc1", page_content="alpha", chunk_id="c1")

        out = await pipeline.stage_join_context({"question": "q", "docs": [doc1]})

        self.assertIn("[Doc1]", out.context or "")
        self.assertEqual(len(out.citations), 1)
        self.assertEqual(out.citations[0]["chunk_id"], "c1")

    async def test_stage_prompt_passes_citations(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())

        out = await pipeline.stage_prompt(
            {"question": "q", "context": "ctx", "citations": [{"id": "S1"}]}
        )

        self.assertEqual(out.citations, [{"id": "S1"}])
        messages = out.prompt.to_messages()
        self.assertTrue(any("q" in getattr(m, "content", "") for m in messages))


class RagChainStreamEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_events_emit_payloads(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        docs = [Document(title="Doc1", page_content="alpha", chunk_id="c1")]

        class DummyRetriever:
            def invoke(self, _q: str, **_kwargs):
                return docs

        pipeline.build_retriever = lambda **_kwargs: DummyRetriever()  # type: ignore[assignment]

        class DummyRerankCfg:
            top_n = 3
            max_candidates = 10
            batch_size = 2
            max_doc_chars = 120

        class DummyReranker:
            _cfg = DummyRerankCfg()

            def rerank(
                self,
                _query: str,
                items: list[Document],
                *,
                job_id: str | None = None,
            ) -> list[Document]:
                return items

        pipeline.reranker = DummyReranker()

        async def fake_compress(
            items: List[Document],
            _query: str,
            *,
            max_context=None,
            use_llm=None,
            job_id: str | None = None,
        ):
            return items, len(items), False

        pipeline.compress_docs = fake_compress  # type: ignore[assignment]

        published: list[dict] = []
        recorded: list[tuple[str, dict]] = []

        async def publish(evt: dict) -> None:
            published.append(evt)

        async def record_event(event_type: str, payload: dict) -> None:
            recorded.append((event_type, payload))

        inputs = {
            "question": "q",
            "rag": {},
            "stream": {
                "publish": publish,
                "record_event": record_event,
                "job_id": "job-1",
                "user_id": "user-1",
                "session_id": "sess-1",
            },
        }

        retrieve_out = await pipeline.stage_retrieve(inputs)
        rerank_out = await pipeline.stage_rerank(retrieve_out)
        mmr_out = await pipeline.stage_mmr(rerank_out)
        _compress_out = await pipeline.stage_compress(mmr_out)

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

        retrieve_done = next(evt for evt in published if evt.get("event") == "rag_retrieve.completed")
        self.assertEqual(retrieve_done.get("hits"), 1)

        rerank_done = next(evt for evt in published if evt.get("event") == "rag_rerank.completed")
        self.assertIn("inputHits", rerank_done)
        self.assertIn("outputHits", rerank_done)
        self.assertEqual(rerank_done.get("rerankTopN"), 3)

        mmr_done = next(evt for evt in published if evt.get("event") == "rag_mmr.completed")
        self.assertIn("mmrK", mmr_done)
        self.assertIn("mmrFetchK", mmr_done)
        self.assertIn("mmrLambda", mmr_done)

        compress_done = next(evt for evt in published if evt.get("event") == "rag_compress.completed")
        self.assertEqual(compress_done.get("heuristicHits"), 1)
        self.assertFalse(compress_done.get("llmApplied"))

        recorded_types = {name for name, _payload in recorded}
        self.assertIn("rag_rerank.completed", recorded_types)
        rerank_payload = next(payload for name, payload in recorded if name == "rag_rerank.completed")
        self.assertIn("inputHits", rerank_payload)
        self.assertNotIn("jobId", rerank_payload)

    async def test_chain_emits_events_and_returns_prompt(self) -> None:
        rag_cfg = RagConfig(max_context=1000)
        pipeline = RagPipeline(settings=rag_cfg, embeddings=DummyEmbeddings())
        docs = [Document(title="Doc1", page_content="alpha", chunk_id="c1")]

        class DummyRetriever:
            def invoke(self, _q: str, **_kwargs):
                return docs

        pipeline.build_retriever = lambda **_kwargs: DummyRetriever()  # type: ignore[assignment]

        class DummyReranker:
            def rerank(
                self,
                _query: str,
                items: list[Document],
                *,
                job_id: str | None = None,
            ) -> list[Document]:
                return items

        pipeline.reranker = DummyReranker()

        async def fake_compress(
            items: List[Document],
            _query: str,
            *,
            max_context=None,
            use_llm=None,
            job_id: str | None = None,
        ):
            return items, len(items), False

        pipeline.compress_docs = fake_compress  # type: ignore[assignment]

        published: list[dict] = []
        recorded: list[str] = []

        async def publish(evt: dict) -> None:
            published.append(evt)

        async def record_event(event_type: str, _payload: dict) -> None:
            recorded.append(event_type)

        chain = pipeline.build()
        result = await chain.ainvoke(
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

        self.assertIsInstance(result, RagState)
        self.assertIsNotNone(result.prompt)
        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.citations[0]["chunk_id"], "c1")

        expected = {
            "rag_search_call.in_progress",
            "rag_search_call.completed",
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
