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
        "app.workers.tasks.generation.*": {"queue": "generation"},
        "app.workers.tasks.build.*": {"queue": "build"},
        "app.workers.tasks.deploy.*": {"queue": "deploy"},
    },
)
