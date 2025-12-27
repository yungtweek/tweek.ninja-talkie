from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .base import BaseTool
from .types import ToolCall, ToolContext, ToolError, ToolName, ToolResult, ToolSpec


class ToolNotFoundError(KeyError):
    pass


@dataclass(frozen=True, slots=True)
class DispatchOptions:
    """Options used by dispatchers/agents.

    Keep this minimal; routing/policy can be layered on top later.
    """

    allowed_tools: Optional[Tuple[ToolName, ...]] = None


class ToolRegistry:
    """In-memory tool registry.

    This is intentionally tiny:
      - register tools
      - list tool specs (for LLM exposure)
      - dispatch calls to tools

    Policy (tool routing by intent, risk, tenant, etc.) should live ABOVE this.
    """

    def __init__(self) -> None:
        self._tools: Dict[ToolName, BaseTool[Any, Any]] = {}

    def register(self, tool: BaseTool[Any, Any]) -> None:
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool

    def register_many(self, tools: Iterable[BaseTool[Any, Any]]) -> None:
        for t in tools:
            self.register(t)

    def get(self, name: ToolName) -> BaseTool[Any, Any]:
        try:
            return self._tools[name]
        except KeyError as e:
            raise ToolNotFoundError(name) from e

    def has(self, name: ToolName) -> bool:
        return name in self._tools

    def list_specs(self, *, allowed_tools: Optional[Sequence[ToolName]] = None) -> List[ToolSpec]:
        if allowed_tools is None:
            return [t.spec for t in self._tools.values()]
        allow = set(allowed_tools)
        return [t.spec for n, t in self._tools.items() if n in allow]

    async def dispatch(
        self,
        ctx: ToolContext,
        call: ToolCall,
        *,
        options: Optional[DispatchOptions] = None,
    ) -> ToolResult[Any]:
        """Dispatch a tool call.

        Note: argument validation is intentionally not implemented here yet.
        Add schema validation (jsonschema/pydantic) in a separate layer.
        """

        if options and options.allowed_tools is not None:
            if call.name not in options.allowed_tools:
                return ToolResult(
                    ok=False,
                    error=ToolError(
                        code="tool_not_allowed",
                        message=f"Tool not allowed in this context: {call.name}",
                        details={"tool": call.name},
                    ),
                )

        if not self.has(call.name):
            return ToolResult(
                ok=False,
                error=ToolError(
                    code="tool_not_found",
                    message=f"Tool not found: {call.name}",
                    details={"tool": call.name},
                ),
            )

        tool = self.get(call.name)

        try:
            # For now, we pass raw arguments dict through.
            # Prefer: parse into a Pydantic model in a higher-level dispatcher.
            return await tool.run(ctx, call.arguments)  # type: ignore[arg-type]
        except Exception as e:
            # Never raise exceptions to the LLM runtime.
            return ToolResult(
                ok=False,
                error=ToolError(
                    code="tool_execution_error",
                    message=str(e),
                    details={"tool": call.name},
                ),
            )


def specs_to_openai_tools(specs: Sequence[ToolSpec]) -> List[Mapping[str, Any]]:
    """Convert ToolSpec list to OpenAI-compatible tool definitions."""

    tools: List[Mapping[str, Any]] = []
    for s in specs:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.parameters_schema,
                },
            }
        )
    return tools
