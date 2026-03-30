"""Dependency Injection фабрики для FastAPI Depends()."""
from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session_maker

# TODO: from app.core.security import verify_keycloak_token
# TODO: from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Выдаёт AsyncSession с автоматическим commit/rollback."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

_redis_pool: Redis | None = None


async def get_redis() -> Redis:
    """Возвращает singleton Redis-клиент (пул соединений).

    TODO: инициализировать пул в lifespan приложения.
    """
    global _redis_pool
    if _redis_pool is None:
        raise RuntimeError("Redis pool не инициализирован. Вызовите init_redis() в lifespan.")
    return _redis_pool


RedisClient = Annotated[Redis, Depends(get_redis)]


# ---------------------------------------------------------------------------
# Current user (from Keycloak JWT)
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Извлекает и валидирует пользователя из Bearer-токена Keycloak.

    TODO: реализовать через app.core.security.verify_keycloak_token()
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    # TODO: payload = await verify_keycloak_token(credentials.credentials)
    # TODO: return payload
    raise NotImplementedError("get_current_user не реализован — нужна интеграция с Keycloak")


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_role(role: str):
    """Dependency: проверяет что у пользователя есть нужная роль."""
    async def _check(user: CurrentUser) -> dict:
        roles: list[str] = user.get("realm_access", {}).get("roles", [])
        if role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return _check
