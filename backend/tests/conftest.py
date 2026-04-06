"""pytest configuration for backend tests."""
import os
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub all packages not installed in the test environment.
# MUST happen before any app module is imported by test files.
# ---------------------------------------------------------------------------

def _stub(name: str) -> MagicMock:
    """Register a MagicMock as a module stub if the module isn't already there."""
    m = MagicMock(name=name)
    sys.modules.setdefault(name, m)
    return sys.modules[name]


# --- minio ---
_minio = _stub("minio")
_minio.Minio = MagicMock  # keep as a callable class-like object

# --- redis ---
_stub("redis")

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
# DeclarativeBase must be a real class so subclassing works.
class _FakeBase:
    pass

_stub("sqlalchemy")
_stub("sqlalchemy.ext")

_sa_asyncio = _stub("sqlalchemy.ext.asyncio")   # create_async_engine etc → MagicMock
_sa_orm = _stub("sqlalchemy.orm")
_sa_orm.DeclarativeBase = _FakeBase              # Project(Base) inherits from real class
_stub("sqlalchemy.sql")

# --- celery ---
# @celery_app.task(bind=True, ...) must keep the original function intact,
# because tests import and call _pipeline / _build directly.
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

# --- asyncpg / aio_pika (transitive deps of SQLAlchemy async drivers) ---
_stub("asyncpg")
_stub("aio_pika")

# ---------------------------------------------------------------------------
# Minimal env vars so Pydantic Settings doesn't fail on import
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
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)
