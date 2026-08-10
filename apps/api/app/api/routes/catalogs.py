from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.db.session import get_db_session
from app.models.identity import UserRole
from app.models.lifecycle import Category, Room
from app.schemas.lifecycle import (
    CatalogCreate,
    CatalogUpdate,
    CategoryRead,
    RoomRead,
)

router = APIRouter(prefix="/catalogs", tags=["catalogs"])


def ensure_editor(auth: AuthContext) -> None:
    if auth.user.role == UserRole.CHILD:
        raise HTTPException(status_code=403, detail="Справочники меняет взрослый")


def required_text(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{label} не может быть пустым")
    return cleaned


def apply_changes(entity: Room | Category, payload: CatalogUpdate) -> None:
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field in {"name", "icon"}:
            value = required_text(value, "Название" if field == "name" else "Значок")
        elif field == "color":
            value = value.upper()
        setattr(entity, field, value)


async def commit_catalog(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Такое название уже существует") from exc


@router.get("/rooms", response_model=list[RoomRead])
async def rooms(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    include_inactive: bool = False,
) -> list[Room]:
    query = select(Room).where(Room.household_id == auth.user.household_id)
    if not include_inactive:
        query = query.where(Room.is_active.is_(True))
    return list(await db.scalars(query.order_by(Room.sort_order, Room.name)))


@router.post("/rooms", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: CatalogCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Room:
    ensure_editor(auth)
    room = Room(
        household_id=auth.user.household_id,
        name=required_text(payload.name, "Название"),
        sort_order=payload.sort_order,
        color=payload.color.upper(),
        icon=required_text(payload.icon, "Значок"),
        is_active=True,
    )
    db.add(room)
    await commit_catalog(db)
    await db.refresh(room)
    return room


@router.patch("/rooms/{room_id}", response_model=RoomRead)
async def update_room(
    room_id: str,
    payload: CatalogUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Room:
    ensure_editor(auth)
    room = await db.scalar(
        select(Room).where(Room.id == room_id, Room.household_id == auth.user.household_id)
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    apply_changes(room, payload)
    await commit_catalog(db)
    await db.refresh(room)
    return room


@router.get("/categories/{domain}", response_model=list[CategoryRead])
async def categories(
    domain: Literal["task", "shopping", "storage"],
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    include_inactive: bool = False,
) -> list[Category]:
    query = select(Category).where(
        Category.household_id == auth.user.household_id,
        Category.domain == domain,
    )
    if not include_inactive:
        query = query.where(Category.is_active.is_(True))
    return list(await db.scalars(query.order_by(Category.sort_order, Category.name)))


@router.post(
    "/categories/{domain}", response_model=CategoryRead, status_code=status.HTTP_201_CREATED
)
async def create_category(
    domain: Literal["task", "shopping", "storage"],
    payload: CatalogCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Category:
    ensure_editor(auth)
    category = Category(
        household_id=auth.user.household_id,
        domain=domain,
        name=required_text(payload.name, "Название"),
        sort_order=payload.sort_order,
        color=payload.color.upper(),
        icon=required_text(payload.icon, "Значок"),
        is_active=True,
        is_default=False,
    )
    db.add(category)
    await commit_catalog(db)
    await db.refresh(category)
    return category


@router.patch("/categories/{domain}/{category_id}", response_model=CategoryRead)
async def update_category(
    domain: Literal["task", "shopping", "storage"],
    category_id: str,
    payload: CatalogUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Category:
    ensure_editor(auth)
    category = await db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.household_id == auth.user.household_id,
            Category.domain == domain,
        )
    )
    if category is None:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    apply_changes(category, payload)
    await commit_catalog(db)
    await db.refresh(category)
    return category
