from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.core.security import opaque_token
from app.db.session import get_db_session
from app.models.identity import User, UserRole
from app.models.storage import StorageItem, StorageNode
from app.schemas.common import Message
from app.schemas.storage import (
    BulkStorageAction,
    DeleteNodeRequest,
    QrRead,
    StorageContents,
    StorageItemCreate,
    StorageItemRead,
    StorageItemUpdate,
    StorageNodeCreate,
    StorageNodeRead,
    StorageNodeUpdate,
    StorageSearchResult,
    StorageTimerExtend,
)
from app.services.auth import now_utc

router = APIRouter(prefix="/storage", tags=["storage"])


def ensure_editor(auth: AuthContext) -> None:
    if auth.user.role == UserRole.CHILD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Кладовую изменяет взрослый"
        )


async def nodes_for_household(db: AsyncSession, household_id: str) -> list[StorageNode]:
    return list(
        await db.scalars(
            select(StorageNode)
            .where(
                StorageNode.household_id == household_id,
                StorageNode.deleted_at.is_(None),
            )
            .order_by(StorageNode.sort_order, StorageNode.name)
        )
    )


def path_for(node_id: str, nodes: dict[str, StorageNode]) -> list[dict[str, str]]:
    path: list[dict[str, str]] = []
    current = nodes.get(node_id)
    visited: set[str] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        path.append({"id": current.id, "name": current.name})
        current = nodes.get(current.parent_id) if current.parent_id else None
    return list(reversed(path))


def read_node(node: StorageNode, nodes: dict[str, StorageNode]) -> StorageNodeRead:
    return StorageNodeRead(
        id=node.id,
        parent_id=node.parent_id,
        name=node.name,
        node_type=node.node_type,
        sort_order=node.sort_order,
        path=path_for(node.id, nodes),
        has_qr=node.qr_token is not None,
    )


def read_item(item: StorageItem, nodes: dict[str, StorageNode]) -> StorageItemRead:
    return StorageItemRead.model_validate(item).model_copy(
        update={"path": path_for(item.node_id, nodes)}
    )


async def load_node(db: AsyncSession, node_id: str, household_id: str) -> StorageNode:
    node = await db.scalar(
        select(StorageNode).where(
            StorageNode.id == node_id,
            StorageNode.household_id == household_id,
            StorageNode.deleted_at.is_(None),
        )
    )
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Раздел не найден")
    return node


async def validate_owner(db: AsyncSession, household_id: str, owner_id: str | None) -> None:
    if owner_id is None:
        return
    exists = await db.scalar(
        select(User.id).where(
            User.id == owner_id,
            User.household_id == household_id,
            User.is_active.is_(True),
        )
    )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Владелец не найден")


@router.get("/tree", response_model=list[StorageNodeRead])
async def storage_tree(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[StorageNodeRead]:
    nodes = await nodes_for_household(db, auth.user.household_id)
    mapping = {node.id: node for node in nodes}
    return [read_node(node, mapping) for node in nodes]


@router.post("/nodes", response_model=StorageNodeRead, status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: StorageNodeCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageNodeRead:
    ensure_editor(auth)
    if payload.parent_id:
        await load_node(db, payload.parent_id, auth.user.household_id)
    node = StorageNode(
        household_id=auth.user.household_id,
        parent_id=payload.parent_id,
        name=payload.name.strip(),
        node_type=payload.node_type.strip(),
        sort_order=payload.sort_order,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    nodes = await nodes_for_household(db, auth.user.household_id)
    return read_node(node, {item.id: item for item in nodes})


def descendant_ids(root_id: str, nodes: list[StorageNode]) -> set[str]:
    result = {root_id}
    while True:
        additions = {
            node.id for node in nodes if node.parent_id in result and node.id not in result
        }
        if not additions:
            return result
        result.update(additions)


@router.patch("/nodes/{node_id}", response_model=StorageNodeRead)
async def update_node(
    node_id: str,
    payload: StorageNodeUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageNodeRead:
    ensure_editor(auth)
    node = await load_node(db, node_id, auth.user.household_id)
    changes = payload.model_dump(exclude_unset=True)
    nodes = await nodes_for_household(db, auth.user.household_id)
    if "parent_id" in changes and changes["parent_id"]:
        await load_node(db, str(changes["parent_id"]), auth.user.household_id)
        if str(changes["parent_id"]) in descendant_ids(node.id, nodes):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя переместить раздел внутрь самого себя",
            )
    for key, value in changes.items():
        setattr(node, key, value.strip() if key in {"name", "node_type"} and value else value)
    await db.commit()
    await db.refresh(node)
    nodes = await nodes_for_household(db, auth.user.household_id)
    return read_node(node, {item.id: item for item in nodes})


@router.get("/nodes/{node_id}/contents", response_model=StorageContents)
async def node_contents(
    node_id: str,
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageContents:
    node = await load_node(db, node_id, auth.user.household_id)
    nodes = await nodes_for_household(db, auth.user.household_id)
    mapping = {item.id: item for item in nodes}
    children = [item for item in nodes if item.parent_id == node.id]
    items = list(
        await db.scalars(
            select(StorageItem)
            .where(
                StorageItem.node_id == node.id,
                StorageItem.archived_at.is_(None),
            )
            .order_by(StorageItem.name)
        )
    )
    return StorageContents(
        node=read_node(node, mapping),
        children=[read_node(item, mapping) for item in children],
        items=[read_item(item, mapping) for item in items],
    )


@router.get("/root", response_model=StorageContents)
async def root_contents(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageContents:
    nodes = await nodes_for_household(db, auth.user.household_id)
    mapping = {item.id: item for item in nodes}
    return StorageContents(
        node=None,
        children=[read_node(item, mapping) for item in nodes if item.parent_id is None],
        items=[],
    )


@router.post("/items", response_model=StorageItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: StorageItemCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageItemRead:
    ensure_editor(auth)
    await load_node(db, payload.node_id, auth.user.household_id)
    await validate_owner(db, auth.user.household_id, payload.owner_id)
    if payload.review_at and payload.review_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Срок хранения должен содержать часовой пояс",
        )
    now = now_utc()
    item = StorageItem(
        household_id=auth.user.household_id,
        name=payload.name.strip(),
        normalized_name=payload.name.strip().casefold(),
        location_since=now,
        review_at=payload.review_at.astimezone(now.tzinfo) if payload.review_at else None,
        review_status="active" if payload.review_at else "none",
        **payload.model_dump(exclude={"name", "review_at"}),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    nodes = await nodes_for_household(db, auth.user.household_id)
    return read_item(item, {node.id: node for node in nodes})


async def load_item(db: AsyncSession, item_id: str, household_id: str) -> StorageItem:
    item = await db.scalar(
        select(StorageItem).where(
            StorageItem.id == item_id,
            StorageItem.household_id == household_id,
            StorageItem.archived_at.is_(None),
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вещь не найдена")
    return item


@router.patch("/items/{item_id}", response_model=StorageItemRead)
async def update_item(
    item_id: str,
    payload: StorageItemUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageItemRead:
    ensure_editor(auth)
    item = await load_item(db, item_id, auth.user.household_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("node_id") and changes["node_id"] != item.node_id:
        await load_node(db, str(changes["node_id"]), auth.user.household_id)
        item.location_since = now_utc()
    if "owner_id" in changes:
        await validate_owner(db, auth.user.household_id, changes["owner_id"])
    for key, value in changes.items():
        setattr(item, key, value.strip() if isinstance(value, str) else value)
    if payload.name:
        item.normalized_name = payload.name.strip().casefold()
    if "review_at" in changes:
        item.review_status = "active" if payload.review_at else "none"
    await db.commit()
    await db.refresh(item)
    nodes = await nodes_for_household(db, auth.user.household_id)
    return read_item(item, {node.id: node for node in nodes})


@router.post("/items/{item_id}/used-today", response_model=StorageItemRead)
async def used_today(
    item_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageItemRead:
    item = await load_item(db, item_id, auth.user.household_id)
    item.last_used_at = now_utc().date()
    await db.commit()
    await db.refresh(item)
    nodes = await nodes_for_household(db, auth.user.household_id)
    return read_item(item, {node.id: node for node in nodes})


@router.post("/items/{item_id}/extend", response_model=StorageItemRead)
async def extend_storage_timer(
    item_id: str,
    payload: StorageTimerExtend,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageItemRead:
    ensure_editor(auth)
    item = await load_item(db, item_id, auth.user.household_id)
    item.review_at = now_utc() + timedelta(days=payload.days)
    item.review_status = "active"
    await db.commit()
    await db.refresh(item)
    nodes = await nodes_for_household(db, auth.user.household_id)
    return read_item(item, {node.id: node for node in nodes})


@router.get("/search", response_model=StorageSearchResult)
async def search_storage(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    q: str = Query(min_length=1, max_length=180),
    node_id: str | None = None,
    scope: str = Query(default="descendants", pattern="^(descendants|level)$"),
) -> StorageSearchResult:
    nodes = await nodes_for_household(db, auth.user.household_id)
    mapping = {node.id: node for node in nodes}
    allowed = set(mapping)
    if node_id:
        await load_node(db, node_id, auth.user.household_id)
        allowed = descendant_ids(node_id, nodes) if scope == "descendants" else {node_id}
    candidates = list(
        await db.scalars(
            select(StorageItem)
            .where(
                StorageItem.household_id == auth.user.household_id,
                StorageItem.node_id.in_(allowed),
                StorageItem.archived_at.is_(None),
            )
            .limit(50000)
        )
    )
    needle = q.strip().casefold()

    def matches(item: StorageItem) -> bool:
        haystack = " ".join(
            filter(
                None,
                [
                    item.name,
                    item.category,
                    item.description,
                    " ".join(item.tags),
                    item.serial_number,
                    item.manufacturer,
                    item.model,
                    " ".join(part["name"] for part in path_for(item.node_id, mapping)),
                ],
            )
        ).casefold()
        return needle in haystack

    found_items = [item for item in candidates if matches(item)][:200]
    found_nodes = [
        node
        for node in nodes
        if node.id in allowed
        and needle in " ".join(p["name"] for p in path_for(node.id, mapping)).casefold()
    ][:200]
    return StorageSearchResult(
        items=[read_item(item, mapping) for item in found_items],
        nodes=[read_node(node, mapping) for node in found_nodes],
    )


@router.post("/nodes/{node_id}/qr", response_model=QrRead)
async def create_qr(
    node_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QrRead:
    ensure_editor(auth)
    node = await load_node(db, node_id, auth.user.household_id)
    if node.qr_token is None:
        node.qr_token = opaque_token(32)
        node.qr_created_at = now_utc()
        await db.commit()
    return QrRead(node_id=node.id, token=node.qr_token, path=f"/storage/qr/{node.qr_token}")


@router.post("/nodes/{node_id}/qr/regenerate", response_model=QrRead)
async def regenerate_qr(
    node_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QrRead:
    ensure_editor(auth)
    node = await load_node(db, node_id, auth.user.household_id)
    node.qr_token = opaque_token(32)
    node.qr_created_at = now_utc()
    await db.commit()
    return QrRead(node_id=node.id, token=node.qr_token, path=f"/storage/qr/{node.qr_token}")


@router.get("/qr/{token}", response_model=StorageContents)
async def qr_contents(
    token: str,
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StorageContents:
    node = await db.scalar(
        select(StorageNode).where(
            StorageNode.qr_token == token,
            StorageNode.household_id == auth.user.household_id,
            StorageNode.deleted_at.is_(None),
        )
    )
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QR недействителен")
    return await node_contents(node.id, auth, db)


@router.post("/bulk", response_model=Message)
async def bulk_action(
    payload: BulkStorageAction,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    ensure_editor(auth)
    items = list(
        await db.scalars(
            select(StorageItem).where(
                StorageItem.id.in_(payload.item_ids),
                StorageItem.household_id == auth.user.household_id,
                StorageItem.archived_at.is_(None),
            )
        )
    )
    if len(items) != len(set(payload.item_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Часть вещей не найдена")
    if payload.action == "move" and payload.node_id:
        await load_node(db, payload.node_id, auth.user.household_id)
        for item in items:
            item.node_id = payload.node_id
            item.location_since = now_utc()
    elif payload.action == "category":
        for item in items:
            item.category = payload.category
    elif payload.action == "owner":
        await validate_owner(db, auth.user.household_id, payload.owner_id)
        for item in items:
            item.owner_id = payload.owner_id
    elif payload.action == "timer":
        for item in items:
            item.review_at = payload.review_at or now_utc() + timedelta(
                days=payload.timer_days or 1
            )
            item.review_status = "active"
    else:
        for item in items:
            item.archived_at = now_utc()
    await db.commit()
    return Message(message=f"Обновлено: {len(items)}")


@router.post("/nodes/{node_id}/delete", response_model=Message)
async def delete_node(
    node_id: str,
    payload: DeleteNodeRequest,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    ensure_editor(auth)
    node = await load_node(db, node_id, auth.user.household_id)
    nodes = await nodes_for_household(db, auth.user.household_id)
    subtree = descendant_ids(node.id, nodes)
    if payload.strategy == "move" and payload.target_node_id:
        if payload.target_node_id in subtree:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя перенести содержимое внутрь удаляемого раздела",
            )
        target = await load_node(db, payload.target_node_id, auth.user.household_id)
        for child in nodes:
            if child.parent_id == node.id:
                child.parent_id = target.id
        items = await db.scalars(select(StorageItem).where(StorageItem.node_id == node.id))
        for item in items:
            item.node_id = target.id
            item.location_since = now_utc()
        subtree = {node.id}
    deleted_at = now_utc()
    for candidate in nodes:
        if candidate.id in subtree:
            candidate.deleted_at = deleted_at
            candidate.purge_after = deleted_at + timedelta(days=30)
    await db.commit()
    return Message(message="Раздел помещён в корзину на 30 дней")
