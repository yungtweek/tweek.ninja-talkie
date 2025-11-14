# apps/workers/chat_worker/settings.py
from pathlib import Path
from typing import Optional
import os
from enum import Enum

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class WeaviateSearchType(str, Enum):
    NEAR_TEXT = "near_text"
    HYBRID = "hybrid"

# RAG-specific configuration (Pydantic v2 submodel)
class RagConfig(BaseModel):
    """RAG-specific configuration (Pydantic v2 submodel).
    Values are optional here and will be backfilled from top-level Settings,
    unless explicitly provided via nested env (RAG__*).
    """
    weaviate_url: Optional[str] = None
    weaviate_api_key: Optional[str] = None
    collection: str = "Chunks"
    text_key: str = "text"
    embedding_model: Optional[str] = None

    top_k: int = 10          # RAG_TOP_K
    mmq: int = 3            # RAG_MMQ
    max_context: int = 3500    # RAG_MAX_CONTEXT
    search_type: WeaviateSearchType = WeaviateSearchType.HYBRID
    alpha: float = 0.6   # hybrid search weighting (0.0 = BM25 only, 1.0 = vector only)
    alpha_multi_strong_max: Optional[float] = 0.45  # multi strong hits → limit keyword bias
    alpha_single_strong_min: Optional[float] = 0.55  # single strong hit → favor vector slightly
    alpha_weak_hit_min: Optional[float] = 0.30       # weak hits → prioritize vector
    alpha_no_bm25_min: Optional[float] = 0.10        # no bm25 hits → vector only

    # ── Retrieval/Scoring knobs
    fusion_type: Optional[str] = "relative"  # "relative" | "ranked" | "default"; used by hybrid retriever
    bm25_query_properties: list[str] = ["text", "text_tri", "filename", "filename_kw"]  # "content" will be rewritten to text_key in validator

    # ── Query normalization / token exclude (Korean-focused)
    normalize_nfc: bool = True
    strip_punct: bool = True
    lowercase_query: bool = False  # keep case for English acronyms; can flip if needed
    ko_min_token_len: int = 2
    ko_keep_english: bool = True   # keep ASCII words (e.g., 'talkie', 'RAG')
    ko_keep_numeric: bool = False
    ko_stop_tokens: list[str] = [
        # 조사/어미
        "은","는","이","가","을","를","에","에서","에게","께","으로","로","과","와","도","만","까지","부터",
        "의","보다","마저","조차","든지","라고","이라고","까지의","같은","하는","된","하여","하게","하며",
        # 접속/불용
        "그리고","그러나","하지만","또","또는","및","또한","그래서","그러므로","때문에","때문","즉","예를","들어",
        # 의문/감탄/형태 보정
        "무엇","어떤","왜","어떻게","하면","해주세요","해주세요.","해줘","알려줘","대해","관련","것","부분","수","대한",
        # 구두어/채움
        "음","어","어어","어허","자","좀","그","이","저","내","너","너희","우리","같아","같은데","요","요.","고마워",
    ]


    rag_prompt: str = (
        "당신은 친절하고 정확한 AI 어시스턴트입니다.\n"
        "- 제공된 Context만으로 답하세요.\n"
        "- Context는 여러 문서 조각으로 구성되어 있으며, 순서와 관계없이 모두 참고하세요.\n"
        "- 모르면 모른다고 말하세요.\n"
        "- 출처가 되는 문서 제목/섹션을 간단히 써주세요.\n"
        "- 출처가 없는 경우 출처를 표기하지 마세요."
    )


class Settings(BaseSettings):
    OPENAI_API_KEY: str | None = None
    DB_URL: str | None = Field(default=None, description="dsn is required")
    LOG_LEVEL: str = "DEBUG"
    NOISY_LEVEL: str = "WARNING"

    APP_NAME: str | None = "chat_worker"
    WEAVIATE_URL: str | None = Field(default=None, description="WEAVIATE_URL is required")
    WEAVIATE_API_KEY: Optional[str] = None
    WEAVIATE_COLLECTION: str = "Chunks"
    BATCH_SIZE: int = 64
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    RAG_TOP_K: int = 10
    RAG_MMQ: int = 3
    RAG_MAX_CONTEXT: int = 3500
    RAG: RagConfig = Field(default_factory=RagConfig)


    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.7
    LLM_TIMEOUT_S: int | None = 90

    MAX_CTX_TOKENS: int | None = None  # 모델 컨텍스트 예산
    MAX_HISTORY_TURNS: int | None = None # 최근 N턴
    SUMMARIZE_THRESHOLD: int | None = None

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
        # Post-process query prop defaults: map placeholder to actual text_key
        if r.bm25_query_properties:
            mapped = [(r.text_key if x == "content" else x) for x in r.bm25_query_properties]
            # de-dup while keeping order
            seen = set()
            r.bm25_query_properties = [x for x in mapped if not (x in seen or seen.add(x))]
        # text_key stays as its own default ("content") unless overridden
        # search_type keeps its own default ("hybrid") unless overridden
        return self

    # ── pydantic v2
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )