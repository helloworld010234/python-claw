"""Configuration loading for the skeleton milestone."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration loaded from environment variables or `.env`."""

    environment: str = Field(default="local", validation_alias="PYTHON_CLAW_ENV")
    database_url: str = Field(
        default="sqlite:///./.claw/python-claw.sqlite3",
        validation_alias="PYTHON_CLAW_DATABASE_URL",
    )
    workspace_root: str = Field(
        default="./workspace",
        validation_alias="PYTHON_CLAW_WORKSPACE_ROOT",
    )
    log_level: str = Field(default="INFO", validation_alias="PYTHON_CLAW_LOG_LEVEL")
    max_turns: int = Field(default=20, validation_alias="PYTHON_CLAW_MAX_TURNS")
    tool_timeout_seconds: int = Field(
        default=30,
        validation_alias="PYTHON_CLAW_TOOL_TIMEOUT_SECONDS",
    )
    tool_max_output_chars: int = Field(
        default=8000,
        validation_alias="PYTHON_CLAW_TOOL_MAX_OUTPUT_CHARS",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
