import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    PORT: int = 8080
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # Google Cloud Settings
    GCP_PROJECT_ID: str = ""
    GCP_LOCATION: str = "us-central1"

    # API Keys
    GEMINI_API_KEY: str = ""

    # ClickHouse Settings
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123  # HTTP interface port for clickhouse-connect
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DATABASE: str = "cinemagent"
    CLICKHOUSE_SECURE: bool = False

    # MCP (Model Context Protocol) Settings
    SEARCH_MCP_URL: Optional[str] = "http://localhost:5005"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate settings instance
settings = Settings()
