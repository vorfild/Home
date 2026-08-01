from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.db.session import SessionFactory, get_db_session
from app.models.identity import UserRole
from app.models.sync import SyncConflict, SyncEvent
from app.schemas.common import Message
from app.schemas.sync import (
    ConflictResolution,
    EntityConflictStatus,
    EntityVersionRead,
    SyncChange,
    SyncChangeResult,
    SyncConflictRead,
    SyncEventRead,
)
from app.services.auth import now_utc
from app.services.sync import (
    apply_fields,
    apply_sync_change,
    entity_state,
    json_value,
    load_entity,
    record_sync_event,
    version_for,
)

router = APIRouter(prefix="/sync", tags=["sync"])


def ensure_editor(auth: AuthContext) -> None:
    if auth.user.role == UserRole.CHILD:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")


@router.get("/version/{entity_type}/{entity_id}", response_model=EntityVersionRead)
async def get_entity_version(
    entity_type: str,
    entity_id: str,
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> EntityVersionRead:
    entity, spec = await load_entity(db, entity_type, entity_id, auth.user.household_id)
    item = await version_for(
        db,
        household_id=auth.user.household_id,
        entity_type=entity_type,
        entity_id=entity_id,
        entity=entity,
        spec=spec,
    )
    conflicts = await db.scalar(
        select(func.count(SyncConflict.id)).where(
            SyncConflict.household_id == auth.user.household_id,
            SyncConflict.entity_type == entity_type,
            SyncConflict.entity_id == entity_id,
            SyncConflict.status == "pending",
        )
    )
    await db.commit()
    return EntityVersionRead(
        entity_type=entity_type,
        entity_id=entity_id,
        version=item.version,
        state=item.state,
        updated_at=item.updated_at,
        changed_by_id=item.last_actor_id,
        has_conflict=bool(conflicts),
    )


@router.post("/changes", response_model=SyncChangeResult)
async def sync_change(
    payload: SyncChange,
    request: Request,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> SyncChangeResult:
    ensure_editor(auth)
    result = await apply_sync_change(
        db,
        household_id=auth.user.household_id,
        user_id=auth.user.id,
        payload=payload,
    )
    request.state.sync_event_recorded = True
    await db.commit()
    return result


@router.get("/conflicts", response_model=list[SyncConflictRead])
async def list_conflicts(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    pending_only: bool = True,
) -> list[SyncConflict]:
    ensure_editor(auth)
    query = select(SyncConflict).where(SyncConflict.household_id == auth.user.household_id)
    if pending_only:
        query = query.where(SyncConflict.status == "pending")
    return list(await db.scalars(query.order_by(SyncConflict.created_at)))


@router.get("/conflicts/entities", response_model=list[EntityConflictStatus])
async def conflicting_entities(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    entity_type: str | None = None,
) -> list[EntityConflictStatus]:
    query = (
        select(
            SyncConflict.entity_type,
            SyncConflict.entity_id,
            func.count(SyncConflict.id),
            func.max(SyncConflict.created_at),
            func.max(SyncConflict.proposed_by_id),
        )
        .where(
            SyncConflict.household_id == auth.user.household_id,
            SyncConflict.status == "pending",
        )
        .group_by(SyncConflict.entity_type, SyncConflict.entity_id)
    )
    if entity_type:
        query = query.where(SyncConflict.entity_type == entity_type)
    rows = (await db.execute(query)).all()
    return [
        EntityConflictStatus(
            entity_type=row[0],
            entity_id=row[1],
            count=int(row[2]),
            latest_changed_at=row[3],
            latest_actor_id=row[4],
        )
        for row in rows
    ]


async def resolve_one(
    db: AsyncSession,
    conflict: SyncConflict,
    auth: AuthContext,
    payload: ConflictResolution,
) -> None:
    entity, spec = await load_entity(
        db, conflict.entity_type, conflict.entity_id, auth.user.household_id
    )
    version = await version_for(
        db,
        household_id=auth.user.household_id,
        entity_type=conflict.entity_type,
        entity_id=conflict.entity_id,
        entity=entity,
        spec=spec,
        lock=True,
    )
    if payload.resolution != "server":
        chosen: Any = (
            conflict.alternative_value
            if payload.resolution == "alternative"
            else payload.manual_value
        )
        apply_fields(conflict.entity_type, entity, {conflict.field_name: chosen})
        version.version += 1
        version.state = entity_state(entity, spec)
        versions = dict(version.field_versions)
        versions[conflict.field_name] = version.version
        version.field_versions = versions
        version.last_actor_id = auth.user.id
        await record_sync_event(
            db,
            household_id=auth.user.household_id,
            entity_type=conflict.entity_type,
            entity_id=conflict.entity_id,
            action="conflict_resolved",
            actor_id=auth.user.id,
            changed_fields=[conflict.field_name],
            version=version.version,
        )
        conflict.manual_value = json_value(payload.manual_value)
    conflict.status = "resolved"
    conflict.resolved_by_id = auth.user.id
    conflict.resolved_at = now_utc()
    conflict.resolution = payload.resolution


@router.post("/conflicts/{conflict_id}/resolve", response_model=Message)
async def resolve_conflict(
    conflict_id: str,
    payload: ConflictResolution,
    request: Request,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    ensure_editor(auth)
    conflict = await db.scalar(
        select(SyncConflict)
        .where(
            SyncConflict.id == conflict_id,
            SyncConflict.household_id == auth.user.household_id,
            SyncConflict.status == "pending",
        )
        .with_for_update()
    )
    if conflict is None:
        raise HTTPException(status_code=404, detail="Конфликт не найден")
    await resolve_one(db, conflict, auth, payload)
    request.state.sync_event_recorded = True
    await db.commit()
    return Message(message="Конфликт разрешён")


@router.post("/conflicts/reject-all", response_model=Message)
async def reject_all_conflicts(
    request: Request,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    if auth.user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Нужны права администратора")
    conflicts = list(
        await db.scalars(
            select(SyncConflict).where(
                SyncConflict.household_id == auth.user.household_id,
                SyncConflict.status == "pending",
            )
        )
    )
    for conflict in conflicts:
        conflict.status = "resolved"
        conflict.resolved_by_id = auth.user.id
        conflict.resolved_at = now_utc()
        conflict.resolution = "server"
    if conflicts:
        await record_sync_event(
            db,
            household_id=auth.user.household_id,
            entity_type="sync_conflicts",
            entity_id=auth.user.household_id,
            action="rejected_all",
            actor_id=auth.user.id,
        )
    request.state.sync_event_recorded = True
    await db.commit()
    return Message(message=f"Отклонено изменений: {len(conflicts)}")


@router.get("/events", response_model=list[SyncEventRead])
async def sync_events(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SyncEvent]:
    return list(
        await db.scalars(
            select(SyncEvent)
            .where(
                SyncEvent.household_id == auth.user.household_id,
                SyncEvent.sequence > after,
            )
            .order_by(SyncEvent.sequence)
            .limit(limit)
        )
    )


@router.get("/stream")
async def sync_stream(
    request: Request,
    auth: Annotated[AuthContext, Depends(current_auth)],
    after: int = Query(default=0, ge=0),
) -> StreamingResponse:
    household_id = auth.user.household_id

    async def events() -> AsyncIterator[str]:
        cursor = after
        idle = 0
        while not await request.is_disconnected():
            async with SessionFactory() as session:
                items = list(
                    await session.scalars(
                        select(SyncEvent)
                        .where(
                            SyncEvent.household_id == household_id,
                            SyncEvent.sequence > cursor,
                        )
                        .order_by(SyncEvent.sequence)
                        .limit(100)
                    )
                )
            if items:
                for item in items:
                    cursor = item.sequence
                    payload = SyncEventRead.model_validate(item).model_dump(mode="json")
                    yield f"id: {cursor}\nevent: change\ndata: {json.dumps(payload)}\n\n"
                idle = 0
            else:
                idle += 1
                if idle >= 10:
                    yield ": heartbeat\n\n"
                    idle = 0
            await asyncio.sleep(2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
