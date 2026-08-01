from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_timezone: str = "Europe/Moscow"
    database_url: str = "postgresql+asyncpg://domovoy:domovoy@localhost:5432/domovoy"
    secret_key: SecretStr = SecretStr("stage-1-not-used")
    log_level: str = "INFO"
    files_dir: Path = Path("var/files")
    backups_dir: Path = Path("var/backups")
    worker_poll_interval_seconds: int = Field(default=30, ge=5, le=3600)

    @field_validator("app_timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("APP_TIMEZONE must be a valid IANA timezone") from exc
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()
