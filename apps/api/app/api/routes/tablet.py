from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import trusted_device
from app.core.security import digest_token, verify_secret
from app.db.session import get_db_session
from app.models.identity import TrustedDevice, User
from app.schemas.identity import (
    AuthResponse,
    TabletLoginRequest,
    TabletStatus,
    TabletUserRead,
    UserRead,
)
from app.services.auth import (
    DEVICE_COOKIE,
    create_session,
    ensure_login_allowed,
    now_utc,
    record_failed_login,
    request_ip,
    set_session_cookies,
)

router = APIRouter(prefix="/tablet", tags=["shared tablet"])


@router.get("/status", response_model=TabletStatus)
async def tablet_status(
    request: Request, db: Annotated[AsyncSession, Depends(get_db_session)]
) -> TabletStatus:
    raw_token = request.cookies.get(DEVICE_COOKIE)
    if not raw_token:
        return TabletStatus(trusted=False)
    device = await db.scalar(
        select(TrustedDevice).where(TrustedDevice.token_hash == digest_token(raw_token))
    )
    if device is None or not device.is_active or device.revoked_at is not None:
        return TabletStatus(trusted=False)
    return TabletStatus(trusted=True, name=device.name)


@router.get("/users", response_model=list[TabletUserRead])
async def tablet_users(
    device: Annotated[TrustedDevice, Depends(trusted_device)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TabletUserRead]:
    users = await db.scalars(
        select(User)
        .where(
            User.household_id == device.household_id,
            User.is_active.is_(True),
            User.pin_hash.is_not(None),
        )
        .order_by(User.name)
    )
    return [TabletUserRead.model_validate(user) for user in users]


@router.post("/login", response_model=AuthResponse)
async def tablet_login(
    payload: TabletLoginRequest,
    request: Request,
    response: Response,
    device: Annotated[TrustedDevice, Depends(trusted_device)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthResponse:
    identifier = f"tablet:{payload.user_id}"
    ip_address = request_ip(request)
    await ensure_login_allowed(db, identifier, ip_address)
    user = await db.scalar(
        select(User).where(
            User.id == payload.user_id,
            User.household_id == device.household_id,
            User.is_active.is_(True),
        )
    )
    if user is None or not verify_secret(payload.pin, user.pin_hash):
        await record_failed_login(db, identifier, ip_address)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный PIN")
    device.last_used_at = now_utc()
    _, session_token, csrf_token = await create_session(
        db, request, user=user, trusted_device=device
    )
    await db.commit()
    set_session_cookies(response, session_token, csrf_token)
    return AuthResponse(user=UserRead.model_validate(user), csrf_token=csrf_token)
