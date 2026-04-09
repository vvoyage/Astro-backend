"""Инициализация Celery — broker RabbitMQ, result backend Redis."""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "astro-worker",
    broker=settings.RABBITMQ_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks.generation",
        "app.workers.tasks.build",
        "app.workers.tasks.deploy",
        "app.workers.tasks.edit",
        "app.workers.tasks.sync_users",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Маршрутизация очередей
    task_routes={
        "generation.run_pipeline": {"queue": "generation"},
        "build.run": {"queue": "build"},
        "deploy.run": {"queue": "deploy"},
        "edit.edit_element": {"queue": "generation"},
    },
    # Периодические задачи (Celery Beat)
    beat_schedule={
        "purge-deleted-keycloak-users": {
            "task": "sync_users.purge_deleted_keycloak_users",
            "schedule": 600,  # каждые 10 минут
        },
    },
)
