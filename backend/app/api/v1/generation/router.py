"""Эндпоинты генерации: запуск пайплайна и SSE-стрим статуса."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.dependencies import CurrentUser, DbSession, RedisClient
from app.schemas.generation import GenerationRequest, GenerationStatus

router = APIRouter(prefix="/generation", tags=["generation"])


@router.post("", response_model=dict)
async def start_generation(
    body: GenerationRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Запускает Celery-задачу генерации, возвращает project_id.

    TODO:
    1. Создать project через repositories.project.create()
    2. Записать начальный статус в Redis
    3. Отправить run_generation_pipeline.delay(...)
    4. Вернуть {project_id, status: "queued"}
    """
    raise NotImplementedError


@router.get("/{project_id}/status")
async def stream_generation_status(
    project_id: UUID,
    redis: RedisClient,
    user: CurrentUser,
) -> StreamingResponse:
    """SSE-стрим статуса генерации.

    Клиент подключается и получает события:
      data: {"stage": "optimizer", "progress": 15, "message": "..."}

    TODO:
    1. Подписаться на Redis pub/sub канал generation:{project_id}
    2. Транслировать события клиенту
    3. Закрыть стрим при stage=done|error
    """
    async def event_generator():
        # TODO: реализовать через Redis pub/sub
        yield "data: {}\n\n"
        await asyncio.sleep(0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
