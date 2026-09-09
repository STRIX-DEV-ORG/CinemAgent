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

    GEMINI_MODEL_VERSION: str = "gemini-3.6-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate settings instance
settings = Settings()
