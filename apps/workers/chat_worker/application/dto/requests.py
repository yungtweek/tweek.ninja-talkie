from __future__ import annotations
from typing import Literal

from chat_worker.application.dto.common import MyBaseModel


class ChatRequest(MyBaseModel):
    """
    Kafka payload shape for `chat.request`.
    """
    job_id: str
    user_id: str
    session_id: str
    message: str
    mode: Literal["gen", "rag"] = "gen"


class TitleRequest(MyBaseModel):
    """
       Kafka payload shape for `chat.title.generate`.
     """
    trace_id: str
    job_id: str
    user_id: str
    session_id: str
    message: str
