from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
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
    database_url: str = "sqlite+aiosqlite:///var/domovoy.db"
    secret_key: SecretStr = SecretStr("")
    log_level: str = "INFO"
    files_dir: Path = Path("var/files")
    backups_dir: Path = Path("var/backups")
    worker_poll_interval_seconds: int = Field(default=30, ge=5, le=3600)
    session_ttl_hours: int = Field(default=24 * 30, ge=1, le=24 * 365)
    cookie_secure: bool = False
    login_attempt_limit: int = Field(default=5, ge=3, le=20)
    login_attempt_window_minutes: int = Field(default=15, ge=1, le=120)
    app_address: str = "http://localhost"
    vapid_public_key: str = ""
    vapid_private_key: SecretStr = SecretStr("")
    vapid_subject: str = "mailto:admin@localhost"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_starttls: bool = True

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

    @model_validator(mode="after")
    def production_requires_secret(self) -> Settings:
        if self.app_env == "production" and len(self.secret_key.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY with at least 32 characters is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
