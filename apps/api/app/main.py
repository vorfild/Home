import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.sync import record_sync_event

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Домовой API",
    version="0.9.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(api_router)


@app.middleware("http")
async def prevent_identity_caching(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    response = await call_next(request)
    identity_prefixes = (
        "/api/v1/auth",
        "/api/v1/setup",
        "/api/v1/family",
        "/api/v1/tablet",
        "/api/v1/settings",
        "/api/v1/files",
        "/api/v1/data",
    )
    if request.url.path.startswith(identity_prefixes):
        response.headers["Cache-Control"] = "no-store"
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and 200 <= response.status_code < 400
        and getattr(request.state, "household_id", None)
        and not getattr(request.state, "sync_event_recorded", False)
    ):
        parts = request.url.path.removeprefix("/api/v1/").split("/")
        entity_type = parts[0] if parts else "unknown"
        entity_id = next(
            (part for part in reversed(parts) if re.fullmatch(r"[0-9a-fA-F-]{36}", part)),
            "/".join(parts[1:]) or entity_type,
        )
        session = request.state.sync_db
        await record_sync_event(
            session,
            household_id=request.state.household_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=request.method.lower(),
            actor_id=request.state.user_id,
        )
        await session.commit()
    return response


@app.get("/health/live", include_in_schema=False)
async def root_liveness() -> dict[str, str]:
    return {"status": "ok", "service": "api"}
