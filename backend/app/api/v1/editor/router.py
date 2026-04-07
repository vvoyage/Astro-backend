"""Эндпоинты редактора: AI-редактирование элементов и прямое обновление файлов."""
from __future__ import annotations

import json

from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, DbSession, RedisClient
from app.schemas.editor import EditElementRequest, EditElementResponse, UpdateFileRequest
from app.workers.tasks.edit import edit_element as edit_element_task

router = APIRouter(prefix="/editor", tags=["editor"])


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
    """Вернуть исходный код файла проекта из MinIO.

    TODO: загрузить через services.storage
    """
    raise NotImplementedError


@router.put("/file")
async def update_file_code(
    body: UpdateFileRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Ручное обновление файла (без AI), создаёт снапшот.

    TODO: сохранить в MinIO + создать снапшот
    """
    raise NotImplementedError
