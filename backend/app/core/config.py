from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    """
    Настройки приложения, читаемые из переменных окружения или .env файла

    Attributes:
        PROJECT_NAME: Название проекта
        DEBUG: Режим отладки
        VERSION: Версия API
        DATABASE_URL: URL подключения к базе данных (async)
        SYNC_DATABASE_URL: URL подключения к базе данных (sync, для миграций)
        REDIS_URL: URL для Redis (Celery backend + кэш статусов)
    """
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

    # RabbitMQ settings
    RABBITMQ_URL: str 

    # Kubernetes settings
    KUBERNETES_NAMESPACE: str 
    KUBERNETES_SERVICE_ACCOUNT: str 
    
    # Node.js builder settings
    NODE_VERSION: str 
    NPM_REGISTRY: str 

    # Конфигурация в Pydantic 2.x
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )

@lru_cache()
def get_settings() -> Settings:
    """
    Создает синглтон настроек приложения
    
    Returns:
        Settings: Объект настроек
    """
    return Settings()

settings = get_settings() 