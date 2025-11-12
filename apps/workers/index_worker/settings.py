# apps/workers/index_worker/settings.py
import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    OPENAI_API_KEY: str = Field(..., description="OpenAI API key is required")
    DATABASE_URL: str = Field(..., description="OpenAI API key is required")

    LOG_LEVEL: str = "DEBUG"
    NOISY_LEVEL: str = "WARNING"

    APP_NAME: Optional[str] = "IndexWorker"
    WEAVIATE_URL: str | None = Field(..., description="WEAVIATE_URL is required")
    WEAVIATE_API_KEY: Optional[str] = None
    WEAVIATE_COLLECTION: str = "Chunks"
    BATCH_SIZE: int = 64
    EMBEDDING_MODEL: str = "text-embedding-3-large"

    S3_ENDPOINT: str  = Field(..., description="S3_ENDPOINT is required")
    S3_ACCESS_KEY: str  = Field(..., description="S3_ACCESS_KEY is required")
    S3_SECRET_KEY: str  = Field(..., description="S3_SECRET_KEY is required")
    S3_REGION: Optional[str] = None
    S3_BUCKET: str  = Field(..., description="S3_BUCKET is required")

    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.7
    LLM_TIMEOUT_S: Optional[int] = 90

    REDIS_URL: str = Field(..., description="REDIS URL is required")
    KAFKA_BOOTSTRAP: str = Field(..., description="KAFKA_BOOTSTRAP is required")

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

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
