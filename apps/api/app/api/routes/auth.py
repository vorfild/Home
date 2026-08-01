from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.core.security import hash_secret, verify_secret
from app.db.session import get_db_session
from app.schemas.common import Message
from app.schemas.identity import AuthResponse, ChangePasswordRequest, LoginRequest, UserRead
from app.services.auth import (
    CSRF_COOKIE,
    authenticate_password,
    clear_session_cookies,
    create_session,
    now_utc,
    request_ip,
    set_session_cookies,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthResponse:
    user = await authenticate_password(
        db, login=payload.login, password=payload.password, ip_address=request_ip(request)
    )
    _, session_token, csrf_token = await create_session(db, request, user=user)
    await db.commit()
    set_session_cookies(response, session_token, csrf_token)
    return AuthResponse(user=UserRead.model_validate(user), csrf_token=csrf_token)


@router.get("/me", response_model=AuthResponse)
async def me(
    request: Request,
    auth: Annotated[AuthContext, Depends(current_auth)],
) -> AuthResponse:
    csrf_token = request.cookies.get(CSRF_COOKIE)
    if not csrf_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна"
        )
    return AuthResponse(user=UserRead.model_validate(auth.user), csrf_token=csrf_token)


@router.post("/logout", response_model=Message)
async def logout(
    response: Response,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    auth.session.revoked_at = now_utc()
    await db.commit()
    clear_session_cookies(response)
    return Message(message="Вы вышли из аккаунта")


@router.post("/change-password", response_model=AuthResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthResponse:
    if not verify_secret(payload.current_password, auth.user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Текущий пароль указан неверно"
        )
    auth.user.password_hash = hash_secret(payload.new_password)
    auth.user.must_change_password = False
    auth.session.revoked_at = now_utc()
    _, session_token, csrf_token = await create_session(db, request, user=auth.user)
    await db.commit()
    set_session_cookies(response, session_token, csrf_token)
    return AuthResponse(user=UserRead.model_validate(auth.user), csrf_token=csrf_token)
