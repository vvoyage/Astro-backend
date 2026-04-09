"""Celery task для полного pipeline генерации: A0 → A1 → A2 → сохранение в MinIO → сборка."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import redis as redis_lib

from app.agents.architect import ArchitectAgent
from app.agents.code_generator import CodeGeneratorAgent
from app.agents.optimizer import OptimizerAgent
from app.core.config import settings
from app.db.database import AsyncSessionFactory, engine
from app.repositories import project as project_repo
from app.repositories import snapshot as snapshot_repo
from app.services.storage import StorageService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generation.run_pipeline", max_retries=2)
def run_generation_pipeline(
    self, project_id: str, user_id: str, prompt: str, ai_model: str, template_prompt: str | None = None
) -> dict:
    """
    Запускает полный pipeline: A0 → A1 → A2 → MinIO → build.
    Прогресс пишется в Redis: generation:{project_id}:status = {"stage": ..., "progress": ...}
    """
    try:
        storage = StorageService()
    except Exception as exc:
        logger.exception("Failed to initialize StorageService for project %s", project_id)
        _set_redis_status(project_id, "failed", 0)
        raise self.retry(exc=exc, countdown=10)

    try:
        asyncio.run(_run_pipeline(project_id, user_id, prompt, ai_model, storage, template_prompt=template_prompt))
    except Exception as exc:
        logger.exception("Generation pipeline failed for project %s: %s", project_id, exc)
        _set_redis_status(project_id, "failed", 0)
        raise self.retry(exc=exc, countdown=10)
    return {"project_id": project_id, "status": "building"}


# ---------------------------------------------------------------------------
# Internal helpers
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


async def _run_pipeline(
    project_id: str, user_id: str, prompt: str, ai_model: str, storage: StorageService, template_prompt: str | None = None
) -> None:
    await engine.dispose()
    await _pipeline(project_id, user_id, prompt, ai_model, storage, template_prompt=template_prompt)


async def _pipeline(
    project_id: str, user_id: str, prompt: str, ai_model: str, storage: StorageService, template_prompt: str | None = None
) -> None:
    async with AsyncSessionFactory() as db:
        await project_repo.update_status(db, UUID(project_id), "generating")
        await db.commit()

    _set_redis_status(project_id, "optimizer", 10)
    logger.info("Pipeline started: project=%s user=%s model=%s", project_id, user_id, ai_model)

    # A0 — разбираем промпт пользователя в структурированную спецификацию
    optimizer = OptimizerAgent(model=ai_model)
    optimizer_input: dict = {"prompt": prompt}
    if template_prompt:
        optimizer_input["template_slug"] = template_prompt
    structured_spec: dict = await optimizer.run(optimizer_input)
    logger.info("A0 structured spec: %s", json.dumps(structured_spec, ensure_ascii=False, indent=2))
    _set_redis_status(project_id, "optimizer", 25)

    # A1 — по спецификации строим список файлов проекта
    _set_redis_status(project_id, "architect", 30)
    architect = ArchitectAgent(model=ai_model)
    file_specs: dict = await architect.run(structured_spec)
    files_list: list[dict] = file_specs.get("files", [])
    if not files_list:
        logger.error("A1 returned empty files list! Full response: %s", file_specs)
    else:
        logger.info("A1 file plan (%d files): %s", len(files_list), json.dumps(files_list, ensure_ascii=False, indent=2))
    _set_redis_status(project_id, "architect", 45)

    # A2 — генерируем код всех файлов параллельно
    _set_redis_status(project_id, "code_generator", 50)
    code_gen = CodeGeneratorAgent(model=ai_model)
    results: list[dict] = await asyncio.gather(
        *[
            code_gen.run({"file": file_spec, "project_spec": structured_spec})
            for file_spec in files_list
        ]
    )
    generated_files: dict[str, str] = {r["path"]: r["content"] for r in results}
    logger.info("A2 generated %d files: %s", len(generated_files), list(generated_files.keys()))
    _set_redis_status(project_id, "code_generator", 65)

    # сохраняем исходники в MinIO
    _set_redis_status(project_id, "saving", 70)
    await storage.save_source_files(user_id, project_id, generated_files)
    logger.info("Source files saved for project %s", project_id)
    _set_redis_status(project_id, "saving", 80)

    # создаём снапшот v1 — начальное состояние проекта (только src/-файлы, остальные не редактируются)
    src_files = {p: c for p, c in generated_files.items() if p.lstrip("/").startswith("src/")}
    async with AsyncSessionFactory() as db:
        for path, content in src_files.items():
            file_path = path.lstrip("/").removeprefix("src/")
            snap_path = f"projects/{user_id}/{project_id}/snapshots/v1/{file_path}"
            await storage.save_file("projects", snap_path, content.encode("utf-8"))
            await snapshot_repo.create(
                db,
                project_id=UUID(project_id),
                version=1,
                minio_path=snap_path,
                description=f"Первоначальная генерация: {prompt[:200]}",
            )
        await project_repo.set_active_snapshot_version(db, UUID(project_id), 1)
        await db.commit()
    logger.info("Initial snapshot v1 created for project %s (%d src files)", project_id, len(src_files))

    # запускаем сборку (импорт здесь, чтобы не было circular import на уровне модуля)
    from app.workers.tasks.build import run_build  # noqa: PLC0415
    run_build.delay(project_id, user_id)
    _set_redis_status(project_id, "building", 85)
    logger.info("Build task queued for project %s", project_id)
