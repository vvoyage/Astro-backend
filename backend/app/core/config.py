from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    """Все настройки берутся из .env файла."""
    PROJECT_NAME: str = "Astro Site Generator"
    DEBUG: bool = False
    VERSION: str = "1.0.0"

    DATABASE_URL: str  # async connection for app
    SYNC_DATABASE_URL: str  # sync connection for migrations
    REDIS_URL: str = "redis://localhost:6379/0"

    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str | None = None  # напр. https://api.proxyapi.ru/openai/v1

    # MinIO settings
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_SECURE: bool
    MINIO_PUBLIC_URL: str
    # Адрес MinIO, доступный из Kubernetes pod'ов (minikube → host)
    # По умолчанию совпадает с MINIO_ENDPOINT, для локальной разработки
    # с minikube нужно указать host.docker.internal:9000
    MINIO_ENDPOINT_K8S: str | None = None

    # RabbitMQ settings
    RABBITMQ_URL: str 

    # Kubernetes settings
    KUBERNETES_NAMESPACE: str
    KUBERNETES_SERVICE_ACCOUNT: str
    # Если True — шаг сборки пропускается, проект сразу помечается "ready".
    # Используется в локальной разработке, когда K8s недоступен.
    BUILD_SKIP: bool = False
    
    # Node.js builder settings
    NODE_VERSION: str 
    NPM_REGISTRY: str 

    # Keycloak settings
    KEYCLOAK_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "astro-service"
    KEYCLOAK_CLIENT_ID: str = "astro-backend"
    # Если False — audience ("aud") в JWT не проверяется.
    # astro-frontend имеет oidc-audience-mapper → "astro-backend" в aud, поэтому True.
    KEYCLOAK_VERIFY_AUDIENCE: bool = True
    # Client secret для service account (client_credentials) — создание пользователей через Admin API
    KEYCLOAK_CLIENT_SECRET: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings() 