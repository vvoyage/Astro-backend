"""Конфигурация pytest для backend-тестов."""
import os
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Заглушки для пакетов, не установленных в тестовом окружении.
# ОБЯЗАТЕЛЬНО до импорта любого модуля приложения в тест-файлах.
# ---------------------------------------------------------------------------

def _stub(name: str) -> MagicMock:
    """Регистрирует MagicMock как заглушку модуля, если модуль ещё не загружен."""
    m = MagicMock(name=name)
    sys.modules.setdefault(name, m)
    return sys.modules[name]


# --- minio ---
_minio = _stub("minio")
_minio.Minio = MagicMock  # оставляем как вызываемый класс-подобный объект
_minio_common = _stub("minio.commonconfig")
_minio_common.CopySource = MagicMock
_minio.commonconfig = _minio_common

# --- redis ---
_redis_mod = _stub("redis")
_redis_asyncio = _stub("redis.asyncio")
_redis_asyncio.Redis = MagicMock
_redis_asyncio.from_url = MagicMock
_redis_mod.asyncio = _redis_asyncio

# --- loguru ---
_loguru = _stub("loguru")
_loguru.logger = MagicMock()

# --- yaml ---
_stub("yaml")

# --- kubernetes ---
_k8s = _stub("kubernetes")
_k8s_client = _stub("kubernetes.client")
_k8s_config = _stub("kubernetes.config")
_k8s.client = _k8s_client
_k8s.config = _k8s_config

# --- sqlalchemy family ---
# DeclarativeBase должен быть настоящим классом, иначе наследование не работает.
class _FakeBase:
    pass

_stub("sqlalchemy")
_stub("sqlalchemy.ext")

_sa_asyncio = _stub("sqlalchemy.ext.asyncio")   # create_async_engine и др. → MagicMock
_sa_orm = _stub("sqlalchemy.orm")
_sa_orm.DeclarativeBase = _FakeBase              # Project(Base) наследуется от настоящего класса
_stub("sqlalchemy.sql")

# --- celery ---
# @celery_app.task(bind=True, ...) должен сохранять оригинальную функцию,
# т.к. тесты импортируют и вызывают _pipeline / _build напрямую.
class _FakeCelery:
    def __init__(self, *args, **kwargs):
        self.conf = MagicMock()

    def task(self, *args, **kwargs):
        def _decorator(fn):
            fn.delay = MagicMock()
            fn.apply_async = MagicMock()
            fn.s = MagicMock()
            return fn
        return _decorator

_celery_mod = _stub("celery")
_celery_mod.Celery = _FakeCelery

# --- asyncpg / aio_pika (транзитивные зависимости async-драйверов SQLAlchemy) ---
_stub("asyncpg")
_stub("aio_pika")

# ---------------------------------------------------------------------------
# Минимальные env vars, чтобы Pydantic Settings не падал при импорте
# ---------------------------------------------------------------------------
_TEST_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "SYNC_DATABASE_URL": "postgresql+psycopg2://test:test@localhost/test",
    "OPENAI_API_KEY": "sk-test-key",
    "MINIO_ENDPOINT": "localhost:9000",
    "MINIO_ACCESS_KEY": "minioadmin",
    "MINIO_SECRET_KEY": "minioadmin",
    "MINIO_SECURE": "false",
    "MINIO_PUBLIC_URL": "http://localhost:9000",
    "RABBITMQ_URL": "amqp://guest:guest@localhost/",
    "KUBERNETES_NAMESPACE": "default",
    "KUBERNETES_SERVICE_ACCOUNT": "default",
    "NODE_VERSION": "20",
    "NPM_REGISTRY": "https://registry.npmjs.org",
    "KEYCLOAK_CLIENT_SECRET": "test-secret",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)
