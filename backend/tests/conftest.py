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

# --- fastapi ---

class _FakeHTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail

class _FakeStatus:
    HTTP_200_OK = 200
    HTTP_201_CREATED = 201
    HTTP_202_ACCEPTED = 202
    HTTP_204_NO_CONTENT = 204
    HTTP_400_BAD_REQUEST = 400
    HTTP_401_UNAUTHORIZED = 401
    HTTP_403_FORBIDDEN = 403
    HTTP_404_NOT_FOUND = 404
    HTTP_409_CONFLICT = 409
    HTTP_422_UNPROCESSABLE_ENTITY = 422
    HTTP_500_INTERNAL_SERVER_ERROR = 500

class _FakeAPIRouter:
    """APIRouter-заглушка: декораторы @router.get/post/put/delete возвращают оригинальную функцию."""
    def __init__(self, *args, **kwargs):
        self.prefix = kwargs.get("prefix", "")
        self.tags = kwargs.get("tags", [])

    def _noop_decorator(self, *args, **kwargs):
        def _wrap(fn):
            return fn
        return _wrap

    get = post = put = delete = patch = options = head = _noop_decorator

_fastapi = _stub("fastapi")
_fastapi.HTTPException = _FakeHTTPException
_fastapi.status = _FakeStatus
_fastapi.APIRouter = _FakeAPIRouter
_fastapi.Depends = lambda *a, **kw: None   
_fastapi.Request = MagicMock
_fastapi.Response = MagicMock

_fastapi_security = _stub("fastapi.security")
_fastapi_security.HTTPBearer = MagicMock
_fastapi_security.HTTPAuthorizationCredentials = MagicMock

# --- app.core.security.keycloak ---
# Нужен для загрузки app.core.dependencies (verify_keycloak_token).
_stub("app.core.security")
_stub("app.core.security.keycloak")

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
