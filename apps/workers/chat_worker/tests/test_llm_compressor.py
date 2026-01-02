import asyncio
import json
import unittest

from chat_worker.application.rag.compressors.llm import LLMCompressorConfig, LLMContextualCompressor
from chat_worker.application.rag.document import Document


class DummyAsyncCompressor(LLMContextualCompressor):
    async def _call_llm_async(
        self,
        prompt: str,
        cfg: LLMCompressorConfig,
        *,
        job_id: str | None = None,
    ) -> str:
        return json.dumps({"kept": "async keep", "dropped": 0})


class LLMCompressorTests(unittest.TestCase):
    def test_compress_docs_ok(self):
        cfg = LLMCompressorConfig(min_keep_chars=3, model="test-model")
        llm = lambda prompt, model=None: json.dumps({"kept": "keep me", "dropped": 2})
        compressor = LLMContextualCompressor(llm, cfg=cfg)
        doc = Document(page_content="original text", metadata={"chunk_id": "c1"})

        out = compressor.compress_docs(query="q", docs=[doc])

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].page_content, "keep me")
        md = out[0].metadata
        self.assertTrue(md.get("compressed"))
        self.assertEqual(md.get("compressor"), "llm")
        self.assertEqual(md.get("compress_model"), "test-model")
        self.assertEqual(md.get("compress_dropped"), 2)

    def test_compress_docs_fallback_on_short(self):
        cfg = LLMCompressorConfig(min_keep_chars=10)
        llm = lambda prompt, model=None: json.dumps({"kept": "short", "dropped": 1})
        compressor = LLMContextualCompressor(llm, cfg=cfg)
        doc = Document(page_content="original text", metadata={"chunk_id": "c1"})

        out = compressor.compress_docs(query="q", docs=[doc])

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].page_content, "original text")
        self.assertNotIn("compressed", out[0].metadata)

    def test_compress_docs_fallback_on_bad_json(self):
        cfg = LLMCompressorConfig(min_keep_chars=3)
        llm = lambda prompt, model=None: "not-json"
        compressor = LLMContextualCompressor(llm, cfg=cfg)
        doc = Document(page_content="original text", metadata={"chunk_id": "c1"})

        out = compressor.compress_docs(query="q", docs=[doc])

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].page_content, "original text")
        self.assertNotIn("compressed", out[0].metadata)

    def test_compress_docs_fail_open_false_raises(self):
        def boom(_prompt, _model=None):
            raise RuntimeError("llm down")

        cfg = LLMCompressorConfig(fail_open=False)
        compressor = LLMContextualCompressor(boom, cfg=cfg)
        doc = Document(page_content="original text", metadata={"chunk_id": "c1"})

        with self.assertRaises(RuntimeError):
            compressor.compress_docs(query="q", docs=[doc])

    def test_compress_docs_callable_signature_prompt_only(self):
        cfg = LLMCompressorConfig(min_keep_chars=3)
        llm = lambda prompt: json.dumps({"kept": "prompt-only", "dropped": 0})
        compressor = LLMContextualCompressor(llm, cfg=cfg)
        doc = Document(page_content="original text", metadata={"chunk_id": "c1"})

        out = compressor.compress_docs(query="q", docs=[doc])

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].page_content, "prompt-only")
        self.assertTrue(out[0].metadata.get("compressed"))

    def test_acompress_docs_ok(self):
        cfg = LLMCompressorConfig(min_keep_chars=3, model="test-model")
        compressor = DummyAsyncCompressor(llm=object(), cfg=cfg)
        doc = Document(page_content="original text", metadata={"chunk_id": "c1"})

        out = asyncio.run(compressor.acompress_docs(query="q", docs=[doc]))

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].page_content, "async keep")
        self.assertTrue(out[0].metadata.get("compressed"))


if __name__ == "__main__":
    unittest.main()
