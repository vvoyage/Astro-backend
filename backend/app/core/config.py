from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache

class Settings(BaseSettings):
    """
    Настройки приложения, читаемые из переменных окружения или .env файла
    
    Attributes:
        PROJECT_NAME: Название проекта
        DEBUG: Режим отладки
        VERSION: Версия API
        DATABASE_URL: URL подключения к базе данных
        SECRET_KEY: Секретный ключ для JWT токенов
        ALGORITHM: Алгоритм для JWT
        ACCESS_TOKEN_EXPIRE_MINUTES: Время жизни access token
    """
    PROJECT_NAME: str = "Astro Site Generator"
    DEBUG: bool = False
    VERSION: str = "1.0.0"
    
    DATABASE_URL: str  # асинхронное подключение для приложения
    SYNC_DATABASE_URL: str  # синхронное подключение для миграций
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    OPENAI_API_KEY: str

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