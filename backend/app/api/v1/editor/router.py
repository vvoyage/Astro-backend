"""Эндпоинты редактора: AI-редактирование элементов и прямое обновление файлов."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import CurrentUser, DbSession, RedisClient
from app.repositories import project as project_repo
from app.repositories import snapshot as snapshot_repo
from app.schemas.editor import EditElementRequest, EditElementResponse, UpdateFileRequest
from app.services.storage import StorageService
from app.workers.tasks.build import run_build as run_build_task
from app.workers.tasks.edit import edit_element as edit_element_task

router = APIRouter(prefix="/editor", tags=["editor"])


@router.get("/files")
async def list_project_files(
    project_id: str,
    user: CurrentUser,
) -> dict:
    """Возвращает список файлов проекта из MinIO (только src/*)."""
    user_id: str = user["internal_user_id"]
    storage = StorageService()
    prefix = f"projects/{user_id}/{project_id}/src/"
    try:
        all_paths = await storage.list_files("projects", prefix)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # Отдаём относительные пути (без prefix) и фильтруем маркеры директорий
    files = [p[len(prefix):] for p in all_paths if not p.endswith("/") and p[len(prefix):]]
    return {"project_id": project_id, "files": files}


@router.post("/edit", response_model=EditElementResponse, status_code=status.HTTP_202_ACCEPTED)
async def edit_element(
    body: EditElementRequest,
    db: DbSession,
    redis: RedisClient,
    user: CurrentUser,
) -> EditElementResponse:
    """Запускает AI-редактирование файла через Celery (A4 EditorAgent).

    Возвращает 202 Accepted немедленно; прогресс читается из
    Redis generation:{project_id}:status (те же SSE что у генерации).
    """
    user_id: str = user["internal_user_id"]

    redis_key = f"generation:{body.project_id}:status"
    await redis.set(
        redis_key,
        json.dumps({"stage": "queued", "progress": 0}),
        ex=86400,
    )

    task = edit_element_task.delay(
        project_id=body.project_id,
        user_id=user_id,
        file_path=body.element.file_path,
        element_id=body.element.editable_id,
        element_html=body.element.element_html,
        prompt=body.instruction,
        ai_model=body.ai_model,
        project_context="",
    )

    return EditElementResponse(
        task_id=str(task.id),
        project_id=body.project_id,
        file_path=body.element.file_path,
        status="queued",
    )


@router.get("/file")
async def get_file_code(
    project_id: str,
    file_path: str,
    user: CurrentUser,
) -> dict:
    """Вернуть исходный код файла проекта из MinIO."""
    user_id: str = user["internal_user_id"]
    storage = StorageService()
    minio_path = f"projects/{user_id}/{project_id}/src/{file_path.lstrip('/')}"
    try:
        raw = await storage.get_file("projects", minio_path)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return {"project_id": project_id, "file_path": file_path, "content": raw.decode("utf-8")}


@router.post("/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild_project(
    project_id: str,
    user: CurrentUser,
    redis: RedisClient,
) -> dict:
    """Запускает пересборку Astro-проекта после ручного редактирования файлов.

    Пишет начальный статус в Redis (чтобы SSE /generation/{id}/status сразу ответил),
    затем ставит Celery-задачу run_build в очередь.
    """
    user_id: str = user["internal_user_id"]
    await redis.set(
        f"generation:{project_id}:status",
        json.dumps({"stage": "building", "progress": 70}),
        ex=86400,
    )
    run_build_task.delay(project_id, user_id)
    return {"status": "queued", "project_id": project_id}


@router.put("/file")
async def update_file_code(
    body: UpdateFileRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Ручное обновление файла (без AI). Сохраняет новое содержимое, затем создаёт снапшот новой версии."""
    user_id: str = user["internal_user_id"]
    storage = StorageService()
    minio_path = f"projects/{user_id}/{body.project_id}/src/{body.file_path.lstrip('/')}"

    new_content = body.content.encode("utf-8")
    await storage.save_file("projects", minio_path, new_content)

    latest_version = await snapshot_repo.get_latest_version(db, UUID(body.project_id))
    new_version = latest_version + 1
    snapshot_path = (
        f"projects/{user_id}/{body.project_id}/snapshots/v{new_version}"
        f"/{body.file_path.lstrip('/')}"
    )
    await storage.save_file("projects", snapshot_path, new_content)
    await snapshot_repo.create(
        db,
        project_id=UUID(body.project_id),
        version=new_version,
        minio_path=snapshot_path,
        description="Manual file update",
    )
    await project_repo.set_active_snapshot_version(db, UUID(body.project_id), new_version)
    await db.commit()

    return {"project_id": body.project_id, "file_path": body.file_path, "status": "saved"}
