from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import digest_token, hash_secret, opaque_token, verify_secret
from app.models.identity import LoginAttempt, Session, TrustedDevice, User

SESSION_COOKIE = "domovoy_session"
CSRF_COOKIE = "domovoy_csrf"
DEVICE_COOKIE = "domovoy_tablet"
CSRF_HEADER = "X-CSRF-Token"

settings = get_settings()
dummy_password_hash = hash_secret("Not-a-real-password-123")


def now_utc() -> datetime:
    return datetime.now(UTC)


def as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def request_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", maxsplit=1)[0].strip()[:64]
    return request.client.host[:64] if request.client else "unknown"


def request_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    return user_agent[:300] if user_agent else None


async def ensure_login_allowed(session: AsyncSession, login: str, ip_address: str) -> None:
    cutoff = now_utc() - timedelta(minutes=settings.login_attempt_window_minutes)
    count = await session.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.attempted_at >= cutoff,
            LoginAttempt.login == login,
            LoginAttempt.ip_address == ip_address,
        )
    )
    if count is not None and count >= settings.login_attempt_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток. Повторите вход через несколько минут",
            headers={"Retry-After": str(settings.login_attempt_window_minutes * 60)},
        )


async def record_failed_login(session: AsyncSession, login: str, ip_address: str) -> None:
    session.add(LoginAttempt(login=login, ip_address=ip_address, attempted_at=now_utc()))
    await session.commit()


async def clear_failed_logins(session: AsyncSession, login: str, ip_address: str) -> None:
    await session.execute(
        delete(LoginAttempt).where(
            LoginAttempt.login == login, LoginAttempt.ip_address == ip_address
        )
    )


async def authenticate_password(
    session: AsyncSession, *, login: str, password: str, ip_address: str
) -> User:
    await ensure_login_allowed(session, login, ip_address)
    user = await session.scalar(select(User).where(User.login == login))
    encoded = user.password_hash if user is not None else dummy_password_hash
    valid = verify_secret(password, encoded)
    if user is None or not valid or not user.is_active:
        await record_failed_login(session, login, ip_address)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    await clear_failed_logins(session, login, ip_address)
    return user


async def create_session(
    db: AsyncSession,
    request: Request,
    *,
    user: User,
    trusted_device: TrustedDevice | None = None,
) -> tuple[Session, str, str]:
    session_token = opaque_token()
    csrf_token = opaque_token(24)
    issued_at = now_utc()
    session = Session(
        user_id=user.id,
        token_hash=digest_token(session_token),
        csrf_hash=digest_token(csrf_token),
        user_agent=request_user_agent(request),
        ip_address=request_ip(request),
        created_at=issued_at,
        last_seen_at=issued_at,
        expires_at=issued_at + timedelta(hours=settings.session_ttl_hours),
        trusted_device_id=trusted_device.id if trusted_device else None,
    )
    db.add(session)
    await db.flush()
    return session, session_token, csrf_token


def set_session_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=settings.cookie_secure, samesite="strict"
    )
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.cookie_secure, samesite="strict")


def set_device_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        DEVICE_COOKIE,
        token,
        max_age=5 * 365 * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
