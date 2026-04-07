"""Эндпоинты генерации: запуск пайплайна и SSE-стрим статуса."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import CurrentUser, DbSession, RedisClient
from app.repositories import project as project_repo
from app.schemas.generation import GenerationRequest
from app.workers.tasks.generation import run_generation_pipeline

router = APIRouter(prefix="/generation", tags=["generation"])

_SSE_POLL_INTERVAL = 0.5
_SSE_TERMINAL_STAGES = frozenset({"done", "error", "failed"})
_SSE_MAX_ITERATIONS = 7200  # ~1 ч при интервале 0.5 с


@router.post("", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def start_generation(
    body: GenerationRequest,
    db: DbSession,
    redis: RedisClient,
    user: CurrentUser,
) -> dict:
    """Создаёт Project, пишет статус queued в Redis, запускает Celery pipeline."""
    user_id = UUID(user["internal_user_id"])
    name = (body.prompt[:60].strip() or "generation").replace("\n", " ")

    project = await project_repo.create(
        db,
        user_id=user_id,
        name=name,
        prompt=body.prompt,
        s3_path="pending",
    )
    project.s3_path = f"projects/{user_id}/{project.id}"
    await db.flush()

    redis_key = f"generation:{project.id}:status"
    await redis.set(
        redis_key,
        json.dumps({"stage": "queued", "progress": 0}),
        ex=86400,
    )

    run_generation_pipeline.delay(
        str(project.id),
        str(user_id),
        body.prompt,
        body.ai_model,
    )

    return {"project_id": str(project.id), "status": "queued"}


@router.get("/{project_id}/status")
async def stream_generation_status(
    project_id: UUID,
    db: DbSession,
    redis: RedisClient,
    user: CurrentUser,
) -> StreamingResponse:
    """SSE-стрим статуса генерации — polling Redis каждые 0.5 с.

    Клиент получает события вида:
      data: {"stage": "optimizer", "progress": 15}
    Стрим закрывается при stage=done|error|failed.
    """
    user_id = UUID(user["internal_user_id"])
    project = await project_repo.get_by_id(db, project_id)
    if project is None or project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    redis_key = f"generation:{project_id}:status"

    async def event_generator():
        iterations = 0
        while iterations < _SSE_MAX_ITERATIONS:
            iterations += 1
            raw = await redis.get(redis_key)
            if raw:
                payload = json.loads(raw)
                yield f"data: {json.dumps(payload)}\n\n"
                if payload.get("stage") in _SSE_TERMINAL_STAGES:
                    break
            else:
                yield f"data: {json.dumps({'stage': 'queued', 'progress': 0})}\n\n"
            await asyncio.sleep(_SSE_POLL_INTERVAL)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
