from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Mapping, Optional, TypeVar

from chat_worker.application.tool.types import ToolContext, ToolResult, ToolSpec

TArgs = TypeVar("TArgs")
TOut = TypeVar("TOut")


class BaseTool(ABC, Generic[TArgs, TOut]):
    """Base class for all tools.

    Tools should be thin:
      - validate/normalize input
      - call repos/clients from ctx.deps
      - return a ToolResult

    Do NOT embed raw SQL here; keep IO in adapters/repos.
    """

    @property
    @abstractmethod
    def spec(self) -> ToolSpec:
        """Static tool definition (name, description, JSON schema, tags)."""

    @abstractmethod
    async def run(self, ctx: ToolContext, args: TArgs) -> ToolResult[TOut]:
        """Execute the tool.

        Args should already be validated/parsed (prefer Pydantic models).
        """


def get_dep(ctx: ToolContext, key: str) -> Any:
    """Small helper for retrieving dependencies from ctx.deps.

    Keeps tools readable and provides a single place to improve errors.
    """

    if key not in ctx.deps:
        raise KeyError(f"Missing dependency in ToolContext.deps: {key}")
    return ctx.deps[key]
