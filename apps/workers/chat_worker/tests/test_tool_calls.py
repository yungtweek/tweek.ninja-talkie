import unittest
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from langchain_core.runnables import RunnableConfig

from chat_worker.application.llm_runner import llm_runner
from chat_worker.application.tool.base import BaseTool
from chat_worker.application.tool.dispatcher import ToolDispatcher
from chat_worker.application.tool.registry import ToolRegistry
from chat_worker.application.tool.types import ToolContext, ToolResult, ToolSpec

_UNSET = object()


class EchoTool(BaseTool[dict[str, Any], dict[str, Any]]):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="echo.tool",
            description="Echo back provided arguments.",
            parameters_schema={
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": ["x"],
                "additionalProperties": False,
            },
            tags=("test",),
            risk="read",
        )

    async def run(self, _ctx: ToolContext, args: dict[str, Any]) -> ToolResult[dict[str, Any]]:
        self.calls.append(dict(args))
        return ToolResult(ok=True, data={"echo": dict(args)})


class DummyLlm:
    provider = "test"
    model = "test"

    def __init__(self) -> None:
        self.calls = 0

    async def astream(
            self,
            _messages: list[Any],
            config: RunnableConfig | None = None,
            tools: Any = None,
    ) -> None:
        self.calls += 1
        callbacks = config.get("callbacks", []) if config is not None else []
        tags = config.get("tags", []) if config is not None else []
        run_id = f"run-{self.calls}"

        if self.calls == 1:
            chunk_msg = AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "echo.tool",
                        "args": {"x": 1},
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
                        "name": "echo.tool",
                        "args": {"x": 1},
                        "id": "call-1",
                    }
                ],
            )
        else:
            chunk_msg = AIMessageChunk(content="OK")
            chunk = ChatGenerationChunk(message=chunk_msg)
            for cb in callbacks:
                on_token = getattr(cb, "on_llm_new_token", None)
                if on_token is not None:
                    await on_token("OK", run_id=run_id, tags=tags, chunk=chunk)

            msg = AIMessage(content="OK")

        result = LLMResult(generations=[[ChatGeneration(message=msg)]])
        for cb in callbacks:
            on_end = getattr(cb, "on_llm_end", None)
            if on_end is not None:
                await on_end(result, run_id=run_id, tags=tags)


class ToolLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_call_then_final_answer_streams_only_final(self) -> None:
        published: list[dict[str, Any]] = []

        async def publish(evt: dict) -> None:
            published.append(evt)

        tool = EchoTool()
        registry = ToolRegistry()
        registry.register(tool)
        dispatcher = ToolDispatcher(registry)

        final = await llm_runner(
            llm=DummyLlm(),
            job_id="job-1",
            user_id="user-1",
            messages=[],
            publish=publish,
            tool_dispatcher=dispatcher,
            on_done=None,
            on_error=None,
        )

        self.assertEqual(tool.calls, [{"x": 1}])
        self.assertEqual(final, "OK")


class ToolExposureTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_not_passed_without_dispatcher(self) -> None:
        class NoToolsDummyLlm:
            provider = "test"
            model = "test"

            def __init__(self) -> None:
                self.tools_arg = _UNSET

            async def astream(
                    self,
                    _messages: list[Any],
                    config: RunnableConfig | None = None,
                    tools: Any = _UNSET,
            ) -> None:
                self.tools_arg = tools
                callbacks = config.get("callbacks", []) if config is not None else []
                tags = config.get("tags", []) if config is not None else []
                run_id = "run-1"
                msg = AIMessage(content="")
                result = LLMResult(generations=[[ChatGeneration(message=msg)]])
                for cb in callbacks:
                    on_end = getattr(cb, "on_llm_end", None)
                    if on_end is not None:
                        await on_end(result, run_id=run_id, tags=tags)

        async def publish(_evt: dict) -> None:
            return None

        llm = NoToolsDummyLlm()
        await llm_runner(
            llm=llm,
            job_id="job-nt-1",
            user_id="user-nt-1",
            messages=[],
            publish=publish,
            tool_specs=[
                ToolSpec(
                    name="metrics.health_snapshot",
                    description="test",
                    parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
                )
            ],
            tool_dispatcher=None,
            on_done=None,
            on_error=None,
        )

        self.assertIs(llm.tools_arg, _UNSET)
