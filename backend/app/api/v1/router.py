"""Агрегатор всех v1-роутеров. Подключается в main.py как include_router(v1_router)."""
from fastapi import APIRouter

from app.api.v1.auth.router import router as auth_router
from app.api.v1.projects.router import router as projects_router
from app.api.v1.templates.router import router as templates_router
from app.api.v1.snapshots.router import router as snapshots_router
from app.api.v1.deployments.router import router as deployments_router
from app.api.v1.generation.router import router as generation_router
from app.api.v1.editor.router import router as editor_router
from app.api.v1.assets.router import router as assets_router

# users/ объединён с auth/ — отдельный роутер не нужен
from app.api.v1.users.router import router as users_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(projects_router)
v1_router.include_router(templates_router)
v1_router.include_router(snapshots_router)
v1_router.include_router(deployments_router)
v1_router.include_router(generation_router)
v1_router.include_router(editor_router)
v1_router.include_router(assets_router)
