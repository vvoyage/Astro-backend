"""Celery tasks: деплой собранного проекта на внешний хостинг."""
from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="deploy.run", max_retries=2)
def run_deploy(self, deployment_id: str, project_id: str, provider: str, config: dict) -> dict:
    """
    Деплоит собранный dist/ на выбранный хостинг.

    Поддерживаемые провайдеры:
    - vercel: Vercel API
    - netlify: Netlify API
    - github-pages: GitHub Pages через API

    TODO: реализовать под каждый провайдер
    """
    raise NotImplementedError(f"run_deploy для провайдера '{provider}' не реализован")
