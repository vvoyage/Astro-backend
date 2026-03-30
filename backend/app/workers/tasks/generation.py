"""Celery tasks: pipeline генерации Astro-сайта A0 → A1 → A2 → save → build."""
from __future__ import annotations

import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generation.run_pipeline", max_retries=2)
def run_generation_pipeline(self, project_id: str, user_id: str, prompt: str, ai_model: str) -> dict:
    """
    Основная задача генерации. Запускает цепочку:
      A0 (optimizer) → A1 (architect) → A2 (code_generator) → save to MinIO → trigger build

    Статус генерации пишется в Redis: generation:{project_id}:status

    TODO: реализовать через asyncio.run() или celery-pool-asyncio
    """
    raise NotImplementedError("run_generation_pipeline не реализован")
