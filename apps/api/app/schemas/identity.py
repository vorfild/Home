from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.security import is_valid_login, normalize_login, validate_password_strength
from app.models.identity import UserRole
from app.schemas.common import ApiModel


class SetupStatus(ApiModel):
    setup_required: bool


class NotificationSetup(BaseModel):
    in_app: bool = True
    web_push: bool = False
    email: bool = False


class InitialSetupRequest(BaseModel):
    language: Literal["ru"] = "ru"
    timezone: str
    household_name: str = Field(min_length=1, max_length=120)
    admin_name: str = Field(min_length=1, max_length=100)
    admin_login: str = Field(min_length=3, max_length=64)
    admin_password: str = Field(min_length=12, max_length=256)
    admin_color: str = Field(default="#5E7FA3", pattern=r"^#[0-9A-Fa-f]{6}$")
    notifications: NotificationSetup = Field(default_factory=NotificationSetup)

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Укажите действительный часовой пояс IANA") from exc
        return value

    @field_validator("admin_login")
    @classmethod
    def login_is_safe(cls, value: str) -> str:
        normalized = normalize_login(value)
        if not is_valid_login(normalized):
            raise ValueError("Логин: 3–64 символа, латиница, цифры, точка, _ или -")
        return normalized

    @field_validator("admin_password")
    @classmethod
    def password_is_strong(cls, value: str) -> str:
        errors = validate_password_strength(value)
        if errors:
            raise ValueError(". ".join(errors))
        return value


class AbsenceRead(ApiModel):
    id: str
    starts_on: date
    ends_on: date
    substitute_user_id: str | None
    note: str | None


class UserRead(ApiModel):
    id: str
    name: str
    login: str
    role: UserRole
    color: str
    avatar_path: str | None
    must_change_password: bool
    is_active: bool
    active_absence: AbsenceRead | None = None


class AuthResponse(ApiModel):
    user: UserRead
    csrf_token: str


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("login")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_login(value)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def password_is_strong(cls, value: str) -> str:
        errors = validate_password_strength(value)
        if errors:
            raise ValueError(". ".join(errors))
        return value


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    login: str = Field(min_length=3, max_length=64)
    role: Literal[UserRole.ADULT, UserRole.CHILD]
    color: str = Field(default="#8DB8A8", pattern=r"^#[0-9A-Fa-f]{6}$")
    child_must_change_password: bool = False

    @field_validator("login")
    @classmethod
    def login_is_safe(cls, value: str) -> str:
        normalized = normalize_login(value)
        if not is_valid_login(normalized):
            raise ValueError("Логин: 3–64 символа, латиница, цифры, точка, _ или -")
        return normalized


class UserCreated(ApiModel):
    user: UserRead
    temporary_password: str


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal[UserRole.ADULT, UserRole.CHILD] | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_active: bool | None = None


class PasswordResetResponse(ApiModel):
    temporary_password: str


class PinSetRequest(BaseModel):
    pin: str = Field(pattern=r"^\d{4,6}$")


class AbsenceCreate(BaseModel):
    starts_on: date
    ends_on: date
    substitute_user_id: str | None = None
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> AbsenceCreate:
        if self.ends_on < self.starts_on:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        return self


class SessionRead(ApiModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
    is_current: bool


class TabletCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TabletRead(ApiModel):
    id: str
    name: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class TabletStatus(ApiModel):
    trusted: bool
    name: str | None = None


class TabletLoginRequest(BaseModel):
    user_id: str
    pin: str = Field(pattern=r"^\d{4,6}$")


class TabletUserRead(ApiModel):
    id: str
    name: str
    color: str
    avatar_path: str | None
