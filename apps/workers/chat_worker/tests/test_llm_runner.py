import json
import unittest
from decimal import Decimal
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from langchain_core.runnables import RunnableConfig

from chat_worker.application.llm_runner import llm_runner
from chat_worker.application.tool.base import BaseTool
from chat_worker.application.tool.dispatcher import ToolDispatcher
from chat_worker.application.tool.registry import ToolRegistry
from chat_worker.application.tool.types import ToolContext, ToolResult, ToolSpec


class DecimalTool(BaseTool[dict[str, Any], dict[str, Any]]):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="decimal.tool",
            description="Return a decimal value.",
            parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        )

    async def run(self, _ctx: ToolContext, _args: dict[str, Any]) -> ToolResult[dict[str, Any]]:
        return ToolResult(ok=True, data={"value": Decimal("1.25")})


class CaptureToolsLlm:
    provider = "test"
    model = "test"

    def __init__(self) -> None:
        self.tools_args: list[Any] = []

    async def astream(
            self,
            _messages: list[Any],
            config: RunnableConfig | None = None,
            tools: Any = None,
    ) -> None:
        self.tools_args.append(tools)
        callbacks = config.get("callbacks", []) if config is not None else []
        tags = config.get("tags", []) if config is not None else []
        run_id = "run-1"
        msg = AIMessage(content="OK")
        chunk = ChatGenerationChunk(message=AIMessageChunk(content="OK"))
        for cb in callbacks:
            on_token = getattr(cb, "on_llm_new_token", None)
            if on_token is not None:
                await on_token("OK", run_id=run_id, tags=tags, chunk=chunk)
        result = LLMResult(generations=[[ChatGeneration(message=msg)]])
        for cb in callbacks:
            on_end = getattr(cb, "on_llm_end", None)
            if on_end is not None:
                await on_end(result, run_id=run_id, tags=tags)


class ToolCallDecimalLlm:
    provider = "test"
    model = "test"

    def __init__(self) -> None:
        self.calls = 0
        self.seen_messages: list[list[Any]] = []

    async def astream(
            self,
            messages: list[Any],
            config: RunnableConfig | None = None,
            tools: Any = None,
    ) -> None:
        self.calls += 1
        self.seen_messages.append(list(messages))
        callbacks = config.get("callbacks", []) if config is not None else []
        tags = config.get("tags", []) if config is not None else []
        run_id = f"run-{self.calls}"

        if self.calls == 1:
            chunk_msg = AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "decimal_tool",
                        "args": {},
                        "id": "call-1",
                    }
                ],
            )
            chunk = ChatGenerationChunk(message=chunk_msg)
            for cb in callbacks:
                on_token = getattr(cb, "on_llm_new_token", None)
                if on_token is not None:
                    await on_token("CALL", run_id=run_id, tags=tags, chunk=chunk)

            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "decimal_tool",
                        "args": {},
                        "id": "call-1",
                    }
                ],
            )
        else:
            chunk_msg = AIMessageChunk(content="DONE")
            chunk = ChatGenerationChunk(message=chunk_msg)
            for cb in callbacks:
                on_token = getattr(cb, "on_llm_new_token", None)
                if on_token is not None:
                    await on_token("DONE", run_id=run_id, tags=tags, chunk=chunk)

            msg = AIMessage(content="DONE")

        result = LLMResult(generations=[[ChatGeneration(message=msg)]])
        for cb in callbacks:
            on_end = getattr(cb, "on_llm_end", None)
            if on_end is not None:
                await on_end(result, run_id=run_id, tags=tags)


class LlmRunnerToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_sanitized_for_llm(self) -> None:
        async def publish(_evt: dict) -> None:
            return None

        registry = ToolRegistry()
        tool = DecimalTool()
        registry.register(tool)
        dispatcher = ToolDispatcher(registry)

        llm = CaptureToolsLlm()
        await llm_runner(
            llm=llm,
            job_id="job-1",
            user_id="user-1",
            messages=[],
            publish=publish,
            tool_dispatcher=dispatcher,
            tool_specs=[tool.spec],
            on_done=None,
            on_error=None,
        )

        self.assertTrue(llm.tools_args)
        tool_def = llm.tools_args[0][0]
        self.assertEqual(tool_def["function"]["name"], "decimal_tool")

    async def test_tool_result_decimal_serialized(self) -> None:
        async def publish(_evt: dict) -> None:
            return None

        registry = ToolRegistry()
        tool = DecimalTool()
        registry.register(tool)
        dispatcher = ToolDispatcher(registry)

        llm = ToolCallDecimalLlm()
        await llm_runner(
            llm=llm,
            job_id="job-2",
            user_id="user-2",
            messages=[],
            publish=publish,
            tool_dispatcher=dispatcher,
            tool_specs=[tool.spec],
            on_done=None,
            on_error=None,
        )

        tool_messages = [
            m for m in llm.seen_messages[1]
            if isinstance(m, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        payload = json.loads(tool_messages[0].content)
        self.assertEqual(payload["data"]["value"], 1.25)
