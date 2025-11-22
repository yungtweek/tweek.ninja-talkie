from __future__ import annotations

from langchain_core.messages import SystemMessage, HumanMessage

from chat_worker.application.dto.requests import TitleRequest
from chat_worker.domain.ports.llm import LlmPort
from chat_worker.infrastructure.repo.postgres_session_repo import PostgresChatSessionRepo


class ChatTitleService:
    """
    Service responsible for generating concise session titles using an LLM,
    updating them in Postgres, and publishing SSE events.

    Concurrency, Kafka consumption, and Redis connection management are handled externally.
    """
    # SYSTEM_PROMPT = """
    #                 You are an AI assistant that generates concise and descriptive session titles based on user questions.
    #                 - Titles must be under 20 characters.
    #                 - Use the main keyword(s) from the question.
    #                 - Write naturally so it feels like a human-written topic, not like documentation.
    #                 - Avoid generic or stiff words like "features", "characteristics", "session", "question".
    #                 - Prefer simple nouns or phrases (e.g. "Lumen X1 launch", "AR headset intro").
    #                 - Always respond in the same language as the User Question.
    #             """
    SYSTEM_PROMPT = """
        당신은 사용자 질문을 기반으로 간결하고 설명적인 세션 제목을 생성하는 AI 어시스턴트입니다.
        규칙:
        - 제목은 20자 이내로 작성할 것.
        - 질문에 등장하는 핵심 키워드를 사용할 것.
        - 문서 스타일이 아닌 자연스럽고 사람처럼 작성할 것.
        - "특징", "특성", "세션", "질문" 같은 딱딱한 표현은 피할 것.
        - 가능한 간단한 명사 또는 짧은 구문 형태로 작성할 것.
        - 사용자 질문의 언어와 동일한 언어로 제목을 작성할 것.
    """

    def __init__(
        self,
        session_repo: PostgresChatSessionRepo,
        llm: LlmPort,
        xadd_session_event,
    ):
        self.session_repo = session_repo
        self.llm = llm
        self.xadd_session_event = xadd_session_event

    async def generate_title(self, req : TitleRequest) -> None:
        """
        Generate a session title based on the user message and update relevant storage and events.
        """

        # 1) Build prompt (same logic as original title_worker)

        # user_prompt = f"""
        #     User Question: {req.message}
        #     Please generate a concise, natural session title under 20 characters following the rules above,
        #     written in the same language as the User Question.
        # """
        user_prompt = f"""
            사용자 질문: {req.message}
            위 규칙을 따르며 20자 이내의 간결하고 자연스러운 세션 제목을 작성해주세요.
            제목은 반드시 사용자 질문과 동일한 언어로 작성해야 합니다.
        """

        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        # 2) LLM call (semaphore/concurrency is handled externally)
        res = await self.llm.ainvoke(messages)
        title = res.content.strip("\"'")

        user_id = req.user_id
        session_id = req.session_id
        job_id = req.job_id

        # 3) Update the session title in Postgres
        await self.session_repo.upsert_session_title(
            user_id=user_id,
            session_id=session_id,
            title=title,
        )

        # 4) Publish SSE event via Redis Stream
        stream_key = f"sse:session:{job_id}:{user_id}:events"
        await self.xadd_session_event(
            stream_key,
            {
                "type": "UPDATED",
                "userId": user_id,
                "session": {
                    "id": session_id,
                    "title": title,
                },
            },
        )
