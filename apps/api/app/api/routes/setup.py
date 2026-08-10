from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_secret
from app.db.session import get_db_session
from app.models.identity import Household, User, UserRole
from app.schemas.identity import AuthResponse, InitialSetupRequest, SetupStatus, UserRead
from app.services.auth import create_session, set_session_cookies
from app.services.catalogs import seed_default_categories

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatus)
async def setup_status(db: Annotated[AsyncSession, Depends(get_db_session)]) -> SetupStatus:
    household_exists = await db.scalar(select(Household.id).limit(1))
    return SetupStatus(setup_required=household_exists is None)


@router.post("", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def initial_setup(
    payload: InitialSetupRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthResponse:
    if await db.scalar(select(Household.id).limit(1)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Настройка уже завершена")

    household = Household(
        name=payload.household_name.strip(),
        language=payload.language,
        timezone=payload.timezone,
        notification_settings=payload.notifications.model_dump(),
    )
    db.add(household)
    await db.flush()
    admin = User(
        household_id=household.id,
        name=payload.admin_name.strip(),
        login=payload.admin_login,
        role=UserRole.ADMIN,
        password_hash=hash_secret(payload.admin_password),
        color=payload.admin_color.upper(),
        password_change_required=True,
        must_change_password=False,
        is_active=True,
    )
    db.add(admin)
    seed_default_categories(db, household.id)
    try:
        await db.flush()
        _, session_token, csrf_token = await create_session(db, request, user=admin)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Настройка уже завершена"
        ) from exc

    set_session_cookies(response, session_token, csrf_token)
    return AuthResponse(user=UserRead.model_validate(admin), csrf_token=csrf_token)
