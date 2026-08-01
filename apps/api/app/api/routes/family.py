from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, admin_auth, admin_csrf_auth, current_auth
from app.core.security import generate_temporary_password, hash_secret, opaque_token
from app.db.session import get_db_session
from app.models.identity import Absence, Household, Session, TrustedDevice, User, UserRole
from app.schemas.common import Message
from app.schemas.identity import (
    AbsenceCreate,
    AbsenceRead,
    PasswordResetResponse,
    PinSetRequest,
    SessionRead,
    TabletCreate,
    TabletRead,
    UserCreate,
    UserCreated,
    UserRead,
    UserUpdate,
)
from app.services.auth import now_utc, set_device_cookie

router = APIRouter(prefix="/family", tags=["family"])


async def household_user(db: AsyncSession, user_id: str, household_id: str) -> User:
    user = await db.scalar(
        select(User).where(User.id == user_id, User.household_id == household_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return user


async def active_absences(
    db: AsyncSession, user_ids: list[str], household_timezone: str
) -> dict[str, Absence]:
    if not user_ids:
        return {}
    today = datetime.now(ZoneInfo(household_timezone)).date()
    result = await db.scalars(
        select(Absence).where(
            Absence.user_id.in_(user_ids), Absence.starts_on <= today, Absence.ends_on >= today
        )
    )
    return {absence.user_id: absence for absence in result}


def read_user(user: User, absence: Absence | None = None) -> UserRead:
    value = UserRead.model_validate(user)
    return value.model_copy(
        update={"active_absence": AbsenceRead.model_validate(absence) if absence else None}
    )


@router.get("/members", response_model=list[UserRead])
async def list_members(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[UserRead]:
    users = list(
        await db.scalars(
            select(User)
            .where(User.household_id == auth.user.household_id)
            .order_by(User.created_at)
        )
    )
    timezone = await db.scalar(
        select(Household.timezone).where(Household.id == auth.user.household_id)
    )
    absences = await active_absences(db, [user.id for user in users], timezone or "Europe/Moscow")
    return [read_user(user, absences.get(user.id)) for user in users]


@router.post("/members", response_model=UserCreated, status_code=status.HTTP_201_CREATED)
async def create_member(
    payload: UserCreate,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserCreated:
    if await db.scalar(select(User.id).where(User.login == payload.login)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Такой логин уже занят")
    temporary_password = generate_temporary_password()
    must_change = payload.role == UserRole.ADULT or payload.child_must_change_password
    user = User(
        household_id=auth.user.household_id,
        name=payload.name.strip(),
        login=payload.login,
        role=payload.role,
        color=payload.color.upper(),
        password_hash=hash_secret(temporary_password),
        password_change_required=must_change,
        must_change_password=must_change,
        is_active=True,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Такой логин уже занят"
        ) from exc
    await db.refresh(user)
    return UserCreated(user=read_user(user), temporary_password=temporary_password)


@router.patch("/members/{user_id}", response_model=UserRead)
async def update_member(
    user_id: str,
    payload: UserUpdate,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    user = await household_user(db, user_id, auth.user.household_id)
    changes = payload.model_dump(exclude_unset=True)
    if user.id == auth.user.id and changes.get("is_active") is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отключить собственную учётную запись",
        )
    for key, value in changes.items():
        setattr(user, key, value.strip() if key == "name" else value)
    if changes.get("is_active") is False:
        await db.execute(
            update(Session)
            .where(Session.user_id == user.id, Session.revoked_at.is_(None))
            .values(revoked_at=now_utc())
        )
    await db.commit()
    await db.refresh(user)
    return read_user(user)


@router.post("/members/{user_id}/reset-password", response_model=PasswordResetResponse)
async def reset_password(
    user_id: str,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> PasswordResetResponse:
    user = await household_user(db, user_id, auth.user.household_id)
    temporary_password = generate_temporary_password()
    user.password_hash = hash_secret(temporary_password)
    user.must_change_password = user.password_change_required
    await db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=now_utc())
    )
    await db.commit()
    return PasswordResetResponse(temporary_password=temporary_password)


@router.put("/members/{user_id}/pin", response_model=Message)
async def set_pin(
    user_id: str,
    payload: PinSetRequest,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    user = await household_user(db, user_id, auth.user.household_id)
    user.pin_hash = hash_secret(payload.pin)
    await db.commit()
    return Message(message="PIN обновлён")


@router.delete("/members/{user_id}/pin", response_model=Message)
async def delete_pin(
    user_id: str,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    user = await household_user(db, user_id, auth.user.household_id)
    user.pin_hash = None
    await db.commit()
    return Message(message="PIN удалён")


@router.get("/members/{user_id}/sessions", response_model=list[SessionRead])
async def list_sessions(
    user_id: str,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[SessionRead]:
    user = await household_user(db, user_id, auth.user.household_id)
    sessions = await db.scalars(
        select(Session)
        .where(
            Session.user_id == user.id, Session.revoked_at.is_(None), Session.expires_at > now_utc()
        )
        .order_by(Session.last_seen_at.desc())
    )
    return [
        SessionRead(
            id=item.id,
            created_at=item.created_at,
            last_seen_at=item.last_seen_at,
            expires_at=item.expires_at,
            user_agent=item.user_agent,
            ip_address=item.ip_address,
            is_current=item.id == auth.session.id,
        )
        for item in sessions
    ]


@router.post("/members/{user_id}/sessions/revoke", response_model=Message)
async def revoke_sessions(
    user_id: str,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    user = await household_user(db, user_id, auth.user.household_id)
    await db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=now_utc())
    )
    await db.commit()
    return Message(message="Активные сессии завершены")


@router.post(
    "/members/{user_id}/absences", response_model=AbsenceRead, status_code=status.HTTP_201_CREATED
)
async def create_absence(
    user_id: str,
    payload: AbsenceCreate,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AbsenceRead:
    user = await household_user(db, user_id, auth.user.household_id)
    if payload.substitute_user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Замещающий должен быть другим человеком",
        )
    if payload.substitute_user_id:
        substitute = await household_user(db, payload.substitute_user_id, auth.user.household_id)
        if not substitute.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Замещающий пользователь отключён"
            )
    overlap = await db.scalar(
        select(Absence.id).where(
            Absence.user_id == user.id,
            Absence.starts_on <= payload.ends_on,
            Absence.ends_on >= payload.starts_on,
        )
    )
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="На эти даты уже задано отсутствие"
        )
    absence = Absence(user_id=user.id, **payload.model_dump())
    db.add(absence)
    await db.commit()
    await db.refresh(absence)
    return AbsenceRead.model_validate(absence)


@router.get("/members/{user_id}/absences", response_model=list[AbsenceRead])
async def list_absences(
    user_id: str,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AbsenceRead]:
    user = await household_user(db, user_id, auth.user.household_id)
    absences = await db.scalars(
        select(Absence).where(Absence.user_id == user.id).order_by(Absence.starts_on.desc())
    )
    return [AbsenceRead.model_validate(absence) for absence in absences]


@router.delete("/members/{user_id}/absences/{absence_id}", response_model=Message)
async def delete_absence(
    user_id: str,
    absence_id: str,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    user = await household_user(db, user_id, auth.user.household_id)
    result = await db.execute(
        delete(Absence).where(Absence.id == absence_id, Absence.user_id == user.id)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отсутствие не найдено")
    await db.commit()
    return Message(message="Период отсутствия удалён")


@router.get("/tablets", response_model=list[TabletRead])
async def list_tablets(
    auth: Annotated[AuthContext, Depends(admin_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TabletRead]:
    devices = await db.scalars(
        select(TrustedDevice)
        .where(TrustedDevice.household_id == auth.user.household_id)
        .order_by(TrustedDevice.created_at.desc())
    )
    return [TabletRead.model_validate(device) for device in devices]


@router.post("/tablets", response_model=TabletRead, status_code=status.HTTP_201_CREATED)
async def register_tablet(
    payload: TabletCreate,
    response: Response,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TabletRead:
    raw_token = opaque_token()
    from app.core.security import digest_token

    device = TrustedDevice(
        household_id=auth.user.household_id,
        name=payload.name.strip(),
        token_hash=digest_token(raw_token),
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    set_device_cookie(response, raw_token)
    return TabletRead.model_validate(device)


@router.delete("/tablets/{device_id}", response_model=Message)
async def revoke_tablet(
    device_id: str,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    device = await db.scalar(
        select(TrustedDevice).where(
            TrustedDevice.id == device_id, TrustedDevice.household_id == auth.user.household_id
        )
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Устройство не найдено")
    device.is_active = False
    device.revoked_at = now_utc()
    await db.execute(
        update(Session)
        .where(Session.trusted_device_id == device.id, Session.revoked_at.is_(None))
        .values(revoked_at=now_utc())
    )
    await db.commit()
    return Message(message="Доверие к устройству отозвано")
