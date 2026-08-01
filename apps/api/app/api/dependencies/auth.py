from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.security import constant_time_digest_matches, digest_token
from app.db.session import get_db_session
from app.models.identity import Session, TrustedDevice, User, UserRole
from app.services.auth import (
    CSRF_COOKIE,
    CSRF_HEADER,
    DEVICE_COOKIE,
    SESSION_COOKIE,
    as_aware,
    now_utc,
)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: Session


async def current_auth(
    request: Request, db: Annotated[AsyncSession, Depends(get_db_session)]
) -> AuthContext:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    stored = await db.scalar(
        select(Session)
        .options(joinedload(Session.user))
        .where(Session.token_hash == digest_token(raw_token))
    )
    if (
        stored is None
        or stored.revoked_at is not None
        or as_aware(stored.expires_at) <= now_utc()
        or not stored.user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна"
        )
    if as_aware(stored.last_seen_at) < now_utc() - timedelta(minutes=5):
        stored.last_seen_at = now_utc()
        await db.commit()
    request.state.household_id = stored.user.household_id
    request.state.user_id = stored.user.id
    request.state.sync_db = db
    return AuthContext(user=stored.user, session=stored)


async def csrf_auth(
    request: Request, auth: Annotated[AuthContext, Depends(current_auth)]
) -> AuthContext:
    header_token = request.headers.get(CSRF_HEADER)
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if (
        not header_token
        or not cookie_token
        or header_token != cookie_token
        or not constant_time_digest_matches(header_token, auth.session.csrf_hash)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ошибка CSRF-проверки")
    return auth


async def admin_auth(auth: Annotated[AuthContext, Depends(current_auth)]) -> AuthContext:
    if auth.user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Нужны права администратора"
        )
    return auth


async def admin_csrf_auth(auth: Annotated[AuthContext, Depends(csrf_auth)]) -> AuthContext:
    if auth.user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Нужны права администратора"
        )
    return auth


async def trusted_device(
    request: Request, db: Annotated[AsyncSession, Depends(get_db_session)]
) -> TrustedDevice:
    raw_token = request.cookies.get(DEVICE_COOKIE)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Устройство не доверено"
        )
    device = await db.scalar(
        select(TrustedDevice).where(TrustedDevice.token_hash == digest_token(raw_token))
    )
    if device is None or not device.is_active or device.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Устройство не доверено"
        )
    return device
