from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class LlmMetadata(_message.Message):
    __slots__ = ("request_id", "trace_id", "session_id", "user_id")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    trace_id: str
    session_id: str
    user_id: str
    def __init__(self, request_id: _Optional[str] = ..., trace_id: _Optional[str] = ..., session_id: _Optional[str] = ..., user_id: _Optional[str] = ...) -> None: ...

class ChatCompletionRequest(_message.Message):
    __slots__ = ("meta", "model", "system_prompt", "user_prompt", "context", "temperature", "max_tokens", "top_p")
    META_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_PROMPT_FIELD_NUMBER: _ClassVar[int]
    USER_PROMPT_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    MAX_TOKENS_FIELD_NUMBER: _ClassVar[int]
    TOP_P_FIELD_NUMBER: _ClassVar[int]
    meta: LlmMetadata
    model: str
    system_prompt: str
    user_prompt: str
    context: str
    temperature: float
    max_tokens: int
    top_p: float
    def __init__(self, meta: _Optional[_Union[LlmMetadata, _Mapping]] = ..., model: _Optional[str] = ..., system_prompt: _Optional[str] = ..., user_prompt: _Optional[str] = ..., context: _Optional[str] = ..., temperature: _Optional[float] = ..., max_tokens: _Optional[int] = ..., top_p: _Optional[float] = ...) -> None: ...

class ChatCompletionResponse(_message.Message):
    __slots__ = ("output_text", "finish_reason", "prompt_tokens", "completion_tokens", "total_tokens", "latency_ms")
    OUTPUT_TEXT_FIELD_NUMBER: _ClassVar[int]
    FINISH_REASON_FIELD_NUMBER: _ClassVar[int]
    PROMPT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    COMPLETION_TOKENS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_TOKENS_FIELD_NUMBER: _ClassVar[int]
    LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    output_text: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    def __init__(self, output_text: _Optional[str] = ..., finish_reason: _Optional[str] = ..., prompt_tokens: _Optional[int] = ..., completion_tokens: _Optional[int] = ..., total_tokens: _Optional[int] = ..., latency_ms: _Optional[int] = ...) -> None: ...

class ChatCompletionChunkResponse(_message.Message):
    __slots__ = ("deltaText", "finishReason", "index", "promptTokens", "completionTokens", "totalTokens", "latencyMs")
    DELTATEXT_FIELD_NUMBER: _ClassVar[int]
    FINISHREASON_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    PROMPTTOKENS_FIELD_NUMBER: _ClassVar[int]
    COMPLETIONTOKENS_FIELD_NUMBER: _ClassVar[int]
    TOTALTOKENS_FIELD_NUMBER: _ClassVar[int]
    LATENCYMS_FIELD_NUMBER: _ClassVar[int]
    deltaText: str
    finishReason: str
    index: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    latencyMs: int
    def __init__(self, deltaText: _Optional[str] = ..., finishReason: _Optional[str] = ..., index: _Optional[int] = ..., promptTokens: _Optional[int] = ..., completionTokens: _Optional[int] = ..., totalTokens: _Optional[int] = ..., latencyMs: _Optional[int] = ...) -> None: ...
