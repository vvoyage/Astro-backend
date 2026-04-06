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

_BUILD_POLL_INTERVAL = 10   # seconds between status checks
_BUILD_TIMEOUT = 300        # max seconds to wait for job completion


@celery_app.task(bind=True, name="build.run", max_retries=1, time_limit=600)
def run_build(self, project_id: str, user_id: str) -> dict:
    """
    1. Создаёт K8s Job через KubernetesService (job копирует dist/ в MinIO внутри контейнера).
    2. Ждёт завершения Job (polling).
    3. Обновляет project.status = "ready" в БД.
    4. Пишет финальный статус в Redis.
    """
    try:
        asyncio.run(engine.dispose())
        asyncio.run(_build(project_id, user_id))
    except Exception as exc:
        logger.exception("Build failed for project %s: %s", project_id, exc)
        _set_redis_status(project_id, "failed", 0)
        raise self.retry(exc=exc, countdown=15)
    return {"project_id": project_id, "status": "ready"}


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


async def _build(project_id: str, user_id: str) -> None:
    k8s = KubernetesService()

    # Create the build Job (the Job script copies dist/ to MinIO itself)
    job_name = await k8s.create_build_job(user_id, project_id)
    logger.info("Created K8s build job %s for project %s", job_name, project_id)
    _set_redis_status(project_id, "building", 87)

    # Poll until Completed or Failed
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

    # Update project status in DB
    async with AsyncSessionFactory() as db:
        await project_repo.update_status(db, UUID(project_id), "ready")
        await db.commit()

    _set_redis_status(project_id, "done", 100)
    logger.info("Project %s is ready", project_id)
