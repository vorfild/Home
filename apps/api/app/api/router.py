from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.family import router as family_router
from app.api.routes.health import router as health_router
from app.api.routes.home import router as home_router
from app.api.routes.setup import router as setup_router
from app.api.routes.shopping import router as shopping_router
from app.api.routes.storage import router as storage_router
from app.api.routes.tablet import router as tablet_router
from app.api.routes.tasks import router as tasks_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(setup_router)
api_router.include_router(auth_router)
api_router.include_router(family_router)
api_router.include_router(tablet_router)
api_router.include_router(tasks_router)
api_router.include_router(shopping_router)
api_router.include_router(storage_router)
api_router.include_router(home_router)
