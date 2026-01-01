from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Literal, Mapping, MutableMapping, Optional, TypeVar, Union

# ----------------------------
# JSON-ish helper types
# ----------------------------
JSONPrimitive = Union[str, int, float, bool, None]
JSONValue = Union[JSONPrimitive, list["JSONValue"], dict[str, "JSONValue"]]
JSONObject = dict[str, JSONValue]

ToolName = str

TData = TypeVar("TData")


# ----------------------------
# Tool contracts
# ----------------------------
@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Static tool definition used to expose tools to an LLM runtime.

    - `parameters_schema` should be a JSON Schema object that validates tool arguments.
    - `result_schema` is optional; it's useful for debugging/validation but not required.
    """

    name: ToolName
    description: str
    parameters_schema: JSONObject
    tags: tuple[str, ...] = ()
    risk: Literal["read", "write", "external"] = "read"
    result_schema: Optional[JSONObject] = None


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool invocation request."""

    name: ToolName
    arguments: Mapping[str, Any] = field(default_factory=dict)
    call_id: Optional[str] = None  # provider-specific id (optional)


@dataclass(frozen=True, slots=True)
class ToolError:
    """Structured error returned by tools.

    Keep this small and stable; it may be surfaced to the UI.
    """

    code: str
    message: str
    details: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True, slots=True)
class ToolResult(Generic[TData]):
    """Result of executing a tool call."""

    ok: bool
    data: Optional[TData] = None
    error: Optional[ToolError] = None
    meta: Mapping[str, Any] = field(default_factory=dict)


# ----------------------------
# Execution context
# ----------------------------
@dataclass(frozen=True, slots=True)
class ToolContext:
    """Execution context passed to tools.

    `deps` is a small DI bag (repos/clients/etc.). Keep it explicit over time.
    """

    trace_id: str
    now_iso: str
    deps: Mapping[str, Any] = field(default_factory=dict)
    # Optional request-scoped values
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    extra: Mapping[str, Any] = field(default_factory=dict)