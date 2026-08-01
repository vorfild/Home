from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Домовой API",
    version="0.7.0",
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
    )
    if request.url.path.startswith(identity_prefixes):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health/live", include_in_schema=False)
async def root_liveness() -> dict[str, str]:
    return {"status": "ok", "service": "api"}
