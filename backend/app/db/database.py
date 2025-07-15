from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Создаем базовый класс для моделей
class Base(DeclarativeBase):
    pass

# Создаем асинхронный движок
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)

# Создаем фабрику сессий
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Dependency для FastAPI
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для внедрения асинхронной сессии БД в эндпоинты FastAPI
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close() 