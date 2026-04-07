"""Celery task: редактирование файла — A4 → снапшот → MinIO → build."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import redis as redis_lib

from app.agents.editor import EditorAgent
from app.core.config import settings
from app.db.database import AsyncSessionFactory, engine
from app.repositories import snapshot as snapshot_repo
from app.services.storage import StorageService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="edit.edit_element", max_retries=2)
def edit_element(
    self,
    project_id: str,
    user_id: str,
    file_path: str,
    element_id: str,
    prompt: str,
    ai_model: str = "gpt-5.4",
    project_context: str = "",
) -> dict:
    """
    1. Скачивает file_path из MinIO.
    2. Создаёт снапшот текущего состояния файла.
    3. A4 (EditorAgent) генерирует новый код.
    4. Сохраняет обновлённый файл в MinIO.
    5. Запускает run_build.delay().

    Прогресс: edit:{project_id}:status = {"stage": ..., "progress": ...}
    """
    try:
        storage = StorageService()
    except Exception as exc:
        logger.exception("Failed to initialize StorageService for project %s", project_id)
        _set_redis_status(project_id, "failed", 0)
        raise self.retry(exc=exc, countdown=10)

    try:
        asyncio.run(engine.dispose())
        asyncio.run(
            _edit(
                project_id=project_id,
                user_id=user_id,
                file_path=file_path,
                element_id=element_id,
                prompt=prompt,
                ai_model=ai_model,
                project_context=project_context,
                storage=storage,
            )
        )
    except Exception as exc:
        logger.exception("Edit task failed for project %s: %s", project_id, exc)
        _set_redis_status(project_id, "failed", 0)
        raise self.retry(exc=exc, countdown=10)

    return {"project_id": project_id, "file_path": file_path, "status": "building"}


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _set_redis_status(project_id: str, stage: str, progress: int) -> None:
    try:
        r = redis_lib.from_url(settings.REDIS_URL)
        r.set(
            f"generation:{project_id}:status",
            json.dumps({"stage": stage, "progress": progress}),
        )
    except Exception:
        logger.warning("Could not write Redis status for project %s", project_id)


async def _edit(
    project_id: str,
    user_id: str,
    file_path: str,
    element_id: str,
    prompt: str,
    ai_model: str,
    project_context: str,
    storage: StorageService,
) -> None:
    _set_redis_status(project_id, "editing", 10)
    logger.info(
        "Edit started: project=%s user=%s file=%s element=%s",
        project_id, user_id, file_path, element_id,
    )

    # 1. Скачать текущий файл из MinIO
    minio_src_path = f"projects/{user_id}/{project_id}/{file_path.lstrip('/')}"
    raw = await storage.get_file("projects", minio_src_path)
    if raw is None:
        raise FileNotFoundError(f"File not found in MinIO: {minio_src_path}")
    current_code = raw.decode("utf-8")
    logger.info("Downloaded file %s (%d bytes)", minio_src_path, len(raw))
    _set_redis_status(project_id, "editing", 20)

    # 2. Создать снапшот текущего состояния
    async with AsyncSessionFactory() as db:
        latest_version = await snapshot_repo.get_latest_version(db, UUID(project_id))
        new_version = latest_version + 1
        snapshot_path = f"projects/{user_id}/{project_id}/snapshots/v{new_version}/{file_path.lstrip('/')}"

        # сохраняем копию файла до правки
        await storage.save_file("projects", snapshot_path, raw)
        logger.info("Snapshot saved: %s", snapshot_path)

        await snapshot_repo.create(
            db,
            project_id=UUID(project_id),
            version=new_version,
            minio_path=snapshot_path,
            description=f"Before edit: {prompt[:200]}",
        )
        await db.commit()
    _set_redis_status(project_id, "editing", 35)

    # 3. A4 — генерируем новый код файла
    agent = EditorAgent(model=ai_model)
    new_code = await agent.edit(
        current_code=current_code,
        element_id=element_id,
        prompt=prompt,
        project_context=project_context,
    )
    logger.info("EditorAgent produced %d chars for %s", len(new_code), file_path)
    _set_redis_status(project_id, "editing", 60)

    # 4. Сохранить обновлённый файл в MinIO
    await storage.save_file("projects", minio_src_path, new_code.encode("utf-8"))
    logger.info("Updated file saved: %s", minio_src_path)
    _set_redis_status(project_id, "building", 70)

    # 5. Запустить сборку
    from app.workers.tasks.build import run_build  # noqa: PLC0415
    run_build.delay(project_id, user_id)
    logger.info("Build task queued for project %s after edit", project_id)
    # build task пишет финальный статус в generation:{project_id}:status сам
