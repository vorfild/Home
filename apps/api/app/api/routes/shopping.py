from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.db.session import get_db_session
from app.models.identity import Household, User, UserRole
from app.models.shopping import ShoppingItem, ShoppingList
from app.schemas.common import Message
from app.schemas.shopping import (
    FrequentItem,
    ProposalDecision,
    ShoppingItemCreate,
    ShoppingItemRead,
    ShoppingItemUpdate,
    ShoppingListComplete,
    ShoppingListCreate,
    ShoppingListRead,
)
from app.services.auth import now_utc

router = APIRouter(prefix="/shopping", tags=["shopping"])


def ensure_adult(auth: AuthContext) -> None:
    if auth.user.role == UserRole.CHILD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Списками управляет взрослый"
        )


async def validate_member(db: AsyncSession, household_id: str, user_id: str | None) -> None:
    if user_id is None:
        return
    exists = await db.scalar(
        select(User.id).where(
            User.id == user_id,
            User.household_id == household_id,
            User.is_active.is_(True),
        )
    )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Участник не найден")


async def load_list(db: AsyncSession, list_id: str, household_id: str) -> ShoppingList:
    shopping_list = await db.scalar(
        select(ShoppingList)
        .options(selectinload(ShoppingList.items))
        .where(ShoppingList.id == list_id, ShoppingList.household_id == household_id)
    )
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Список не найден")
    return shopping_list


def read_item(item: ShoppingItem, *, duplicate_warning: bool = False) -> ShoppingItemRead:
    return ShoppingItemRead.model_validate(item).model_copy(
        update={"duplicate_warning": duplicate_warning}
    )


def read_list(shopping_list: ShoppingList, current_user_id: str) -> ShoppingListRead:
    accepted = [item for item in shopping_list.items if item.proposal_status == "accepted"]
    accepted.sort(
        key=lambda item: (
            0 if item.recipient_id == current_user_id else 1 if item.recipient_id is None else 2,
            item.recipient_id or "",
            item.category,
            item.created_at,
        )
    )
    prices = [item.price for item in accepted if item.price is not None and item.purchased]
    total = sum(prices, Decimal("0")) if prices else None
    return ShoppingListRead(
        id=shopping_list.id,
        title=shopping_list.title,
        store=shopping_list.store,
        scheduled_at=shopping_list.scheduled_at,
        responsible_id=shopping_list.responsible_id,
        status=shopping_list.status,
        comment=shopping_list.comment,
        completed_at=shopping_list.completed_at,
        items=[read_item(item) for item in accepted],
        total=total,
    )


@router.post("/lists", response_model=ShoppingListRead, status_code=status.HTTP_201_CREATED)
async def create_list(
    payload: ShoppingListCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShoppingListRead:
    ensure_adult(auth)
    await validate_member(db, auth.user.household_id, payload.responsible_id)
    if payload.scheduled_at and payload.scheduled_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Дата покупки должна содержать часовой пояс",
        )
    list_status = "planned" if payload.scheduled_at else "no_date"
    shopping_list = ShoppingList(
        household_id=auth.user.household_id,
        title=payload.title.strip(),
        store=payload.store.strip() if payload.store else None,
        scheduled_at=payload.scheduled_at.astimezone(UTC) if payload.scheduled_at else None,
        responsible_id=payload.responsible_id,
        status=list_status,
        comment=payload.comment.strip() if payload.comment else None,
    )
    db.add(shopping_list)
    await db.commit()
    return read_list(await load_list(db, shopping_list.id, auth.user.household_id), auth.user.id)


@router.get("/lists", response_model=list[ShoppingListRead])
async def list_shopping_lists(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    view: str = Query(default="current", pattern="^(current|planned|history)$"),
) -> list[ShoppingListRead]:
    query = (
        select(ShoppingList)
        .options(selectinload(ShoppingList.items))
        .where(ShoppingList.household_id == auth.user.household_id)
    )
    if view == "current":
        query = query.where(ShoppingList.status.in_(["no_date", "in_progress"]))
    elif view == "planned":
        query = query.where(ShoppingList.status == "planned")
    else:
        query = query.where(ShoppingList.status == "completed")
    items = list(await db.scalars(query.order_by(ShoppingList.scheduled_at.asc().nulls_last())))
    return [read_list(item, auth.user.id) for item in items]


@router.get("/today", response_model=list[ShoppingListRead])
async def today_shopping(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ShoppingListRead]:
    timezone_name = await db.scalar(
        select(Household.timezone).where(Household.id == auth.user.household_id)
    )
    timezone = ZoneInfo(timezone_name or "Europe/Moscow")
    local_date = datetime.now(timezone).date()
    start = datetime.combine(local_date, time.min, timezone).astimezone(UTC)
    end = datetime.combine(local_date + timedelta(days=1), time.min, timezone).astimezone(
        UTC
    ) - timedelta(microseconds=1)
    lists = list(
        await db.scalars(
            select(ShoppingList)
            .options(selectinload(ShoppingList.items))
            .where(
                ShoppingList.household_id == auth.user.household_id,
                ShoppingList.scheduled_at >= start,
                ShoppingList.scheduled_at <= end,
                ShoppingList.status.in_(["planned", "in_progress"]),
            )
            .order_by(ShoppingList.scheduled_at)
        )
    )
    return [read_list(item, auth.user.id) for item in lists]


@router.post(
    "/lists/{list_id}/items", response_model=ShoppingItemRead, status_code=status.HTTP_201_CREATED
)
async def add_item(
    list_id: str,
    payload: ShoppingItemCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShoppingItemRead:
    shopping_list = await load_list(db, list_id, auth.user.household_id)
    if shopping_list.status == "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Список уже завершён")
    await validate_member(db, auth.user.household_id, payload.recipient_id)
    if payload.client_operation_id:
        existing = await db.scalar(
            select(ShoppingItem).where(
                ShoppingItem.client_operation_id == payload.client_operation_id
            )
        )
        if existing:
            return read_item(existing)
    normalized = payload.name.strip().casefold()
    duplicate = await db.scalar(
        select(ShoppingItem.id)
        .join(ShoppingList)
        .where(
            ShoppingList.household_id == auth.user.household_id,
            ShoppingList.status != "completed",
            ShoppingItem.purchased.is_(False),
            ShoppingItem.proposal_status != "rejected",
            ShoppingItem.normalized_name == normalized,
        )
        .limit(1)
    )
    item = ShoppingItem(
        list_id=shopping_list.id,
        name=payload.name.strip(),
        normalized_name=normalized,
        quantity=payload.quantity,
        unit=payload.unit.strip(),
        category=payload.category.strip(),
        note=payload.note.strip() if payload.note else None,
        added_by_id=auth.user.id,
        recipient_id=payload.recipient_id,
        photo_id=payload.photo_id,
        price=payload.price,
        store=payload.store.strip() if payload.store else None,
        proposal_status="pending" if auth.user.role == UserRole.CHILD else "accepted",
        client_operation_id=payload.client_operation_id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return read_item(item, duplicate_warning=duplicate is not None)


async def load_item(
    db: AsyncSession, item_id: str, household_id: str
) -> tuple[ShoppingItem, ShoppingList]:
    item = await db.scalar(
        select(ShoppingItem)
        .join(ShoppingList)
        .options(selectinload(ShoppingItem.shopping_list))
        .where(ShoppingItem.id == item_id, ShoppingList.household_id == household_id)
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Позиция не найдена")
    return item, item.shopping_list


@router.patch("/items/{item_id}", response_model=ShoppingItemRead)
async def update_item(
    item_id: str,
    payload: ShoppingItemUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShoppingItemRead:
    item, shopping_list = await load_item(db, item_id, auth.user.household_id)
    if item.proposal_status != "accepted" or shopping_list.status == "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Позицию нельзя изменить")
    changes = payload.model_dump(exclude_unset=True)
    if auth.user.role == UserRole.CHILD and set(changes) - {"purchased"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    for key, value in changes.items():
        setattr(item, key, value.strip() if key == "note" and value else value)
    if shopping_list.status == "planned" and changes.get("purchased") is not None:
        shopping_list.status = "in_progress"
    await db.commit()
    await db.refresh(item)
    return read_item(item)


@router.get("/proposals", response_model=list[ShoppingItemRead])
async def list_proposals(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ShoppingItemRead]:
    ensure_adult(auth)
    items = await db.scalars(
        select(ShoppingItem)
        .join(ShoppingList)
        .where(
            ShoppingList.household_id == auth.user.household_id,
            ShoppingItem.proposal_status == "pending",
        )
        .order_by(ShoppingItem.created_at)
    )
    return [read_item(item) for item in items]


@router.post("/proposals/{item_id}/decision", response_model=ShoppingItemRead)
async def decide_proposal(
    item_id: str,
    payload: ProposalDecision,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShoppingItemRead:
    ensure_adult(auth)
    item, _ = await load_item(db, item_id, auth.user.household_id)
    if item.proposal_status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Запрос уже обработан")
    item.proposal_status = "accepted" if payload.decision == "accept" else "rejected"
    item.decided_by_id = auth.user.id
    item.decided_at = now_utc()
    await db.commit()
    await db.refresh(item)
    return read_item(item)


@router.get("/frequent", response_model=list[FrequentItem])
async def frequent_items(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=10, ge=1, le=50),
) -> list[FrequentItem]:
    count = func.count(ShoppingItem.id).label("item_count")
    rows = (
        await db.execute(
            select(ShoppingItem.name, ShoppingItem.category, ShoppingItem.unit, count)
            .join(ShoppingList)
            .where(
                ShoppingList.household_id == auth.user.household_id,
                ShoppingItem.proposal_status == "accepted",
            )
            .group_by(ShoppingItem.name, ShoppingItem.category, ShoppingItem.unit)
            .order_by(count.desc())
            .limit(limit)
        )
    ).all()
    return [
        FrequentItem(name=name, category=category, unit=unit, count=item_count)
        for name, category, unit, item_count in rows
    ]


@router.post("/lists/{list_id}/complete", response_model=ShoppingListRead)
async def complete_list(
    list_id: str,
    payload: ShoppingListComplete,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShoppingListRead:
    ensure_adult(auth)
    shopping_list = await load_list(db, list_id, auth.user.household_id)
    unpurchased = [
        item
        for item in shopping_list.items
        if not item.purchased and item.proposal_status == "accepted"
    ]
    if payload.unpurchased == "keep" and unpurchased:
        shopping_list.status = "no_date"
        shopping_list.scheduled_at = None
    else:
        if payload.unpurchased == "move" and payload.target_list_id:
            target = await load_list(db, payload.target_list_id, auth.user.household_id)
            if target.id == shopping_list.id or target.status == "completed":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Выберите другой активный список",
                )
            for item in unpurchased:
                item.list_id = target.id
        elif payload.unpurchased == "remove" and unpurchased:
            await db.execute(
                delete(ShoppingItem).where(ShoppingItem.id.in_([i.id for i in unpurchased]))
            )
        shopping_list.status = "completed"
        shopping_list.completed_at = now_utc()
    await db.commit()
    return read_list(await load_list(db, shopping_list.id, auth.user.household_id), auth.user.id)


@router.delete("/items/{item_id}", response_model=Message)
async def delete_item(
    item_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    item, _ = await load_item(db, item_id, auth.user.household_id)
    if auth.user.role == UserRole.CHILD and item.added_by_id != auth.user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    await db.delete(item)
    await db.commit()
    return Message(message="Позиция удалена")
