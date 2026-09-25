"""Typed application settings loaded from environment variables and `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OpenAI ---
    openai_api_key: SecretStr
    # Two-tier models: strong model for research, cheap model for triage routing.
    openai_model_research: str = "gpt-5"
    openai_model_triage: str = "gpt-5-mini"

    # --- Slack (optional here; required only by the Slack adapter) ---
    slack_bot_token: SecretStr | None = None
    slack_app_token: SecretStr | None = None
    slack_signing_secret: SecretStr | None = None
    slack_mode: Literal["socket", "http"] = "socket"
    slack_http_port: int = 3000
    slash_response_visibility: Literal["public", "ephemeral"] = "public"
    # Comma-separated channel IDs; empty means every channel is allowed.
    allowed_channel_ids: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Tools ---
    github_token: SecretStr | None = None
    http_timeout_seconds: float = 15.0
    tool_cache_ttl_seconds: int = 900

    # --- Agent runtime ---
    agent_max_turns: int = 12
    agent_timeout_seconds: float = 120.0
    session_db_path: Path = Path("data/sessions.sqlite3")

    # --- Observability ---
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("allowed_channel_ids", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (loaded once)."""
    return Settings()
