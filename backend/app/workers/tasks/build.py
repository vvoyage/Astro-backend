"""Celery tasks: сборка Astro-проекта в Docker/K8s-контейнере."""
from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="build.run", max_retries=1, time_limit=300)
def run_build(self, project_id: str, user_id: str) -> dict:
    """
    Запускает K8s Job для сборки: `astro build` внутри Node.js контейнера.
    После сборки загружает dist/ в MinIO bucket astro-projects/{user_id}/{project_id}/build/

    TODO: использовать kubernetes client для создания Job из шаблона infrastructure/k8s/builder-pod.yaml
    """
    raise NotImplementedError("run_build не реализован")
