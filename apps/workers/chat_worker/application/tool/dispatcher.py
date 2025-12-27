from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .registry import DispatchOptions, ToolRegistry
from .types import ToolCall, ToolContext, ToolError, ToolResult

TArgs = TypeVar("TArgs", bound=BaseModel)


class ToolDispatcher:
    """
    High-level dispatcher responsible for:
      - validating tool arguments (Pydantic)
      - enforcing per-call policies
      - delegating execution to ToolRegistry

    This sits BETWEEN the LLM runtime and ToolRegistry.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        # Optional: map tool_name -> Pydantic args model
        self._arg_models: Dict[str, Type[BaseModel]] = {}

    def register_args_model(self, tool_name: str, model: Type[TArgs]) -> None:
        """
        Register a Pydantic model for validating/parsing tool arguments.
        """
        self._arg_models[tool_name] = model

    async def dispatch(
        self,
        ctx: ToolContext,
        call: ToolCall,
        *,
        options: Optional[DispatchOptions] = None,
    ) -> ToolResult[Any]:
        """
        Validate arguments (if a model is registered) and dispatch the call.
        """

        # 1) Validate / parse arguments if a model is registered
        parsed_args: Any = call.arguments
        model = self._arg_models.get(call.name)

        if model is not None:
            try:
                parsed_args = model.model_validate(call.arguments)
            except ValidationError as e:
                return ToolResult(
                    ok=False,
                    error=ToolError(
                        code="tool_argument_validation_error",
                        message="Invalid tool arguments",
                        details=e.errors(),
                    ),
                )

        # 2) Delegate execution to registry
        return await self._registry.dispatch(
            ctx,
            ToolCall(
                name=call.name,
                arguments=parsed_args,
                call_id=call.call_id,
            ),
            options=options,
        )