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
    NARRATIVE_API_URL: str = os.getenv("NARRATIVE_API_URL", "")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate settings instance
settings = Settings()
