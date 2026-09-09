import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    PORT: int = 8080

    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # ClickHouse Settings
    CLICKHOUSE_HOST: str = os.getenv("CLICKHOUSE_HOST")
    CLICKHOUSE_PORT: int = os.getenv("CLICKHOUSE_PORT")
    CLICKHOUSE_USER: str = os.getenv("CLICKHOUSE_USER")
    CLICKHOUSE_SECURE: bool = os.getenv("CLICKHOUSE_SECURE")
    CLICKHOUSE_PASSWORD: str = os.getenv("CLICKHOUSE_PASSWORD")
    CLICKHOUSE_DATABASE: str = os.getenv("CLICKHOUSE_DATABASE")

    # Parallel Web Search API Settings (3rd party service)
    PARALLEL_API_KEY: str = os.getenv("PARALLEL_API_KEY", "")

    # Narrative Graph API settings
    NARRATIVE_API_KEY: str = os.getenv("NARRATIVE_API_KEY")
    NARRATIVE_ADMIN_API_KEY: str = os.getenv("NARRATIVE_ADMIN_API_KEY", "")
    NARRATIVE_API_URL: str = os.getenv("NARRATIVE_API_URL", "")
    NARRATIVE_READ_PROJECTIONS: bool = os.getenv("NARRATIVE_READ_PROJECTIONS", "false").lower() == "true"
    NARRATIVE_PROJECTOR_IN_PROCESS: bool = os.getenv("NARRATIVE_PROJECTOR_IN_PROCESS", "false").lower() == "true"
    NARRATIVE_AGENT_WORKER_IN_PROCESS: bool = os.getenv("NARRATIVE_AGENT_WORKER_IN_PROCESS", "false").lower() == "true"

    GEMINI_MODEL_VERSION: str = "gemini-3.6-flash"
    # Media models intentionally do not inherit the text model.  Text-only
    # Gemini models cannot return image/audio bytes and otherwise trigger a
    # misleading local fallback artifact.
    GEMINI_IMAGE_MODEL: str = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    GEMINI_TTS_MODEL: str = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    GEMINI_MEDIA_ALLOW_FALLBACK: bool = os.getenv("GEMINI_MEDIA_ALLOW_FALLBACK", "false").lower() == "true"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate settings instance
settings = Settings()
