# apps/workers/chat_worker/settings.py
from pathlib import Path
from typing import Optional
import os

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


# RAG-specific configuration (Pydantic v2 submodel)
class RagConfig(BaseModel):
    """RAG-specific configuration (Pydantic v2 submodel).
    Values are optional here and will be backfilled from top-level Settings,
    unless explicitly provided via nested env (RAG__*).
    """
    weaviate_url: Optional[str] = None
    weaviate_api_key: Optional[str] = None
    collection: Optional[str] = None
    text_key: Optional[str] = "content"
    embedding_model: Optional[str] = None

    top_k: Optional[int] = None          # RAG_TOP_K
    mmq: Optional[int] = None            # RAG_MMQ
    max_context: Optional[int] = None    # RAG_MAX_CONTEXT
    search_type: Optional[str] = "similarity"  # or "hybrid"

    rag_prompt: str = (
        "당신은 친절하고 정확한 AI 어시스턴트입니다.\n"
        "- 제공된 Context만으로 답하세요.\n"
        "- 모르면 모른다고 말하세요.\n"
        "- 출처가 되는 문서 제목/섹션을 간단히 써주세요.\n"
        "- 출처가 없는 경우 출처를 표기하지 마세요."
    )


class Settings(BaseSettings):
    OPENAI_API_KEY: str | None = None
    DB_URL: str | None = None
    LOG_LEVEL: str = "DEBUG"
    NOISY_LEVEL: str = "WARNING"

    APP_NAME: str | None = "chat_worker"
    WEAVIATE_URL: str | None = Field(..., description="WEAVIATE_URL is required")
    WEAVIATE_API_KEY: Optional[str] = None
    WEAVIATE_COLLECTION: str = "Chunks"
    BATCH_SIZE: int = 64
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_TOP_K: int = 6
    RAG_MMQ: int = 3
    RAG_MAX_CONTEXT: int = 3500
    RAG: RagConfig = Field(default_factory=RagConfig)

    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.7
    LLM_TIMEOUT_S: int | None = 90

    MAX_CTX_TOKENS: int  # 모델 컨텍스트 예산
    MAX_HISTORY_TURNS: int  # 최근 N턴
    SUMMARIZE_THRESHOLD: int

    REDIS_URL: str = "redis://localhost:6379"
    KAFKA_BOOTSTRAP: str = "localhost:29092"


    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        if os.getenv("APP_ENV") == "production":
            return env_settings, init_settings, file_secret_settings

        return env_settings, init_settings, file_secret_settings, dotenv_settings

    @model_validator(mode="after")
    def _merge_rag_from_top_level(self):
        # Only fill None values in the submodel to respect nested env overrides (RAG__*)
        r = self.RAG
        if r.weaviate_url is None:
            r.weaviate_url = self.WEAVIATE_URL
        if r.weaviate_api_key is None:
            r.weaviate_api_key = self.WEAVIATE_API_KEY
        if r.collection is None:
            r.collection = self.WEAVIATE_COLLECTION
        if r.embedding_model is None:
            r.embedding_model = self.EMBEDDING_MODEL
        if r.top_k is None:
            r.top_k = self.RAG_TOP_K
        if r.mmq is None:
            r.mmq = self.RAG_MMQ
        if r.max_context is None:
            r.max_context = self.RAG_MAX_CONTEXT
        # text_key stays as its own default ("content") unless overridden
        # search_type keeps its own default ("similarity") unless overridden
        return self

    # ── pydantic v2
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )