"""Celery tasks: сборка Astro-проекта в Docker/K8s-контейнере."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import redis as redis_lib

from app.core.config import settings
from app.db.database import AsyncSessionFactory, engine
from app.repositories import project as project_repo
from app.services.kubernetes import KubernetesService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_BUILD_POLL_INTERVAL = 10   # секунды между проверками статуса
_BUILD_TIMEOUT = 600        # максимальное время ожидания завершения job'а


_BUILD_LOCK_TTL = _BUILD_TIMEOUT + 120   # лок истекает даже если воркер упал


@celery_app.task(bind=True, name="build.run", max_retries=10, time_limit=900)
def run_build(self, project_id: str, user_id: str) -> dict:
    """
    1. Захватывает Redis-лок на project_id, чтобы одновременно выполнялся только один билд.
    2. Создаёт K8s Job через KubernetesService (job копирует dist/ в MinIO внутри контейнера).
    3. Ждёт завершения Job (polling).
    4. Обновляет project.status = "ready" в БД.
    5. Пишет финальный статус в Redis.
    """
    r = redis_lib.from_url(settings.REDIS_URL)
    lock = r.lock(f"build:{project_id}:lock", timeout=_BUILD_LOCK_TTL, blocking=False)

    if not lock.acquire(blocking=False):
        # Для этого проекта уже идёт билд — повторим попытку позже
        logger.info("Build already running for project %s, will retry in 60s", project_id)
        raise self.retry(exc=RuntimeError("Build locked"), countdown=60)

    try:
        asyncio.run(_run(project_id, user_id))
    except Exception as exc:
        logger.exception("Build failed for project %s: %s", project_id, exc)
        _set_redis_status(project_id, "failed", 0)
        raise self.retry(exc=exc, countdown=15)
    finally:
        try:
            lock.release()
        except Exception:
            pass  # лок мог уже истечь

    return {"project_id": project_id, "status": "ready"}


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _set_redis_status(project_id: str, stage: str, progress: int, **extra) -> None:
    try:
        r = redis_lib.from_url(settings.REDIS_URL)
        payload = {"stage": stage, "progress": progress, **extra}
        r.set(
            f"generation:{project_id}:status",
            json.dumps(payload),
        )
    except Exception:
        logger.warning("Could not write Redis status for project %s", project_id)


async def _run(project_id: str, user_id: str) -> None:
    await engine.dispose()
    await _build(project_id, user_id)


async def _build(project_id: str, user_id: str) -> None:
    if settings.BUILD_SKIP:
        logger.info("BUILD_SKIP=True, skipping K8s build for project %s", project_id)
        async with AsyncSessionFactory() as db:
            await project_repo.update_status(db, UUID(project_id), "ready")
            await db.commit()
        preview_url = f"{settings.MINIO_PUBLIC_URL}/astro-projects/projects/{user_id}/{project_id}/build/index.html"
        _set_redis_status(project_id, "done", 100, preview_url=preview_url)
        return

    k8s = KubernetesService()

    # Создаём build Job (скрипт внутри job'а сам копирует dist/ в MinIO)
    job_name = await k8s.create_build_job(user_id, project_id)
    logger.info("Created K8s build job %s for project %s", job_name, project_id)
    _set_redis_status(project_id, "building", 87)

    # Опрашиваем статус до Completed или Failed
    waited = 0
    while waited < _BUILD_TIMEOUT:
        await asyncio.sleep(_BUILD_POLL_INTERVAL)
        waited += _BUILD_POLL_INTERVAL

        status = await k8s.get_job_status(job_name)
        logger.debug("Job %s status: %s (%ds elapsed)", job_name, status, waited)

        if status == "Completed":
            break
        if status == "Failed":
            logs = await k8s.get_pod_logs(job_name)
            logger.error("Build job %s failed. Logs:\n%s", job_name, logs)
            raise RuntimeError(f"Build job {job_name} failed. See logs above.")
    else:
        raise TimeoutError(f"Build job {job_name} did not finish within {_BUILD_TIMEOUT}s")

    logger.info("Build job %s completed for project %s", job_name, project_id)
    _set_redis_status(project_id, "building", 95)

    # Обновляем статус проекта в БД
    async with AsyncSessionFactory() as db:
        await project_repo.update_status(db, UUID(project_id), "ready")
        await db.commit()

    preview_url = f"{settings.MINIO_PUBLIC_URL}/astro-projects/projects/{user_id}/{project_id}/build/index.html"
    _set_redis_status(project_id, "done", 100, preview_url=preview_url)
    logger.info("Project %s is ready, preview_url=%s", project_id, preview_url)
