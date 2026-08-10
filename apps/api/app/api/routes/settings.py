from __future__ import annotations

from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.identity import Household, User, UserRole
from app.models.preferences import Notification, PushSubscription
from app.schemas.common import Message
from app.schemas.settings import (
    ModuleSettings,
    NotificationRead,
    PreferenceRead,
    PreferenceUpdate,
    PushKey,
    PushSubscriptionCreate,
    ServerSettingsRead,
    ServerSettingsUpdate,
)
from app.services.auth import now_utc
from app.services.notifications import preference_for

router = APIRouter(prefix="/settings", tags=["settings"])


def ensure_admin(auth: AuthContext) -> None:
    if auth.user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Нужны права администратора"
        )


async def get_household(db: AsyncSession, household_id: str) -> Household:
    item = await db.scalar(select(Household).where(Household.id == household_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Семья не найдена")
    return item


@router.get("/preferences", response_model=PreferenceRead)
async def get_preferences(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreferenceRead:
    item = await preference_for(db, auth.user.id)
    await db.commit()
    return PreferenceRead.model_validate(item)


@router.put("/preferences", response_model=PreferenceRead)
async def update_preferences(
    payload: PreferenceUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreferenceRead:
    item = await preference_for(db, auth.user.id)
    changes = payload.model_dump(mode="python")
    if auth.user.role == UserRole.CHILD:
        for key in (
            "channels",
            "event_rules",
            "reminder_minutes",
            "repeat_minutes",
            "quiet_start",
            "quiet_end",
            "email",
        ):
            changes.pop(key, None)
    for key, value in changes.items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return PreferenceRead.model_validate(item)


@router.put("/preferences/{user_id}", response_model=PreferenceRead)
async def update_member_preferences(
    user_id: str,
    payload: PreferenceUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreferenceRead:
    ensure_admin(auth)
    exists = await db.scalar(
        select(User.id).where(User.id == user_id, User.household_id == auth.user.household_id)
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    item = await preference_for(db, user_id)
    for key, value in payload.model_dump(mode="python").items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return PreferenceRead.model_validate(item)


@router.get("/modules", response_model=ModuleSettings)
async def get_modules(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ModuleSettings:
    house = await get_household(db, auth.user.household_id)
    return ModuleSettings.model_validate({**ModuleSettings().model_dump(), **house.module_settings})


@router.put("/modules", response_model=ModuleSettings)
async def update_modules(
    payload: ModuleSettings,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ModuleSettings:
    ensure_admin(auth)
    house = await get_household(db, auth.user.household_id)
    house.module_settings = payload.model_dump()
    house.meters_enabled = payload.meters
    await db.commit()
    return payload


@router.get("/server", response_model=ServerSettingsRead)
async def get_server_settings(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServerSettingsRead:
    ensure_admin(auth)
    house = await get_household(db, auth.user.household_id)
    settings = get_settings()
    domain = house.server_settings.get("domain") or settings.app_address
    return ServerSettingsRead(
        timezone=house.timezone,
        domain=domain,
        https_enabled=str(domain).startswith("https://") or settings.cookie_secure,
        files_dir=str(settings.files_dir),
        app_version="0.9.0",
        web_push_configured=bool(
            settings.vapid_public_key and settings.vapid_private_key.get_secret_value()
        ),
        smtp_configured=bool(settings.smtp_host and settings.smtp_from),
    )


@router.put("/server", response_model=ServerSettingsRead)
async def update_server_settings(
    payload: ServerSettingsUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServerSettingsRead:
    ensure_admin(auth)
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Неизвестный часовой пояс") from exc
    house = await get_household(db, auth.user.household_id)
    house.timezone = payload.timezone
    house.server_settings = {**house.server_settings, "domain": payload.domain}
    await db.commit()
    return await get_server_settings(auth, db)


@router.get("/notifications", response_model=list[NotificationRead])
async def list_notifications(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    unread_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == auth.user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    return list(await db.scalars(query.order_by(Notification.created_at.desc()).limit(limit)))


@router.get("/notifications/unread-count")
async def unread_count(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, int]:
    value = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == auth.user.id, Notification.read_at.is_(None)
        )
    )
    return {"count": int(value or 0)}


@router.post("/notifications/{notification_id}/read", response_model=Message)
async def read_notification(
    notification_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    item = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == auth.user.id
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    item.read_at = now_utc()
    await db.commit()
    return Message(message="Уведомление прочитано")


@router.post("/notifications/read-all", response_model=Message)
async def read_all_notifications(
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    items = await db.scalars(
        select(Notification).where(
            Notification.user_id == auth.user.id, Notification.read_at.is_(None)
        )
    )
    moment = now_utc()
    for item in items:
        item.read_at = moment
    await db.commit()
    return Message(message="Все уведомления прочитаны")


@router.get("/push/key", response_model=PushKey)
async def push_key() -> PushKey:
    settings = get_settings()
    enabled = bool(settings.vapid_public_key and settings.vapid_private_key.get_secret_value())
    return PushKey(enabled=enabled, public_key=settings.vapid_public_key or None)


@router.post("/push/subscriptions", response_model=Message, status_code=201)
async def subscribe_push(
    payload: PushSubscriptionCreate,
    request: Request,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    existing = await db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    if existing is None:
        existing = PushSubscription(user_id=auth.user.id, **payload.model_dump())
        db.add(existing)
    else:
        existing.user_id = auth.user.id
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
        existing.is_active = True
        existing.failed_attempts = 0
    existing.user_agent = request.headers.get("user-agent", "")[:300] or None
    await db.commit()
    return Message(message="Web Push подключён")


@router.delete("/push/subscriptions", response_model=Message)
async def unsubscribe_push(
    payload: PushSubscriptionCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    item = await db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.user_id == auth.user.id,
        )
    )
    if item is not None:
        item.is_active = False
        await db.commit()
    return Message(message="Web Push отключён")
