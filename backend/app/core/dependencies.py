"""DI-зависимости для FastAPI: БД, Redis, текущий пользователь."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security.keycloak import verify_keycloak_token
from app.db.database import get_async_session
from app.db.models.user import User

_bearer = HTTPBearer(auto_error=True)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DbSession = Annotated[AsyncSession, Depends(get_async_session)]


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

_redis_client: Redis | None = None


async def init_redis() -> None:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_from_url(settings.REDIS_URL, decode_responses=True)


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_redis() -> Redis:
    """Отдаёт singleton Redis-клиент. Инициализируется при старте через lifespan."""
    if _redis_client is None:
        raise RuntimeError("Redis не инициализирован — init_redis() должен вызываться при старте.")
    return _redis_client


RedisClient = Annotated[Redis, Depends(get_redis)]


# ---------------------------------------------------------------------------
# Current user (Keycloak JWT)
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Проверяет Keycloak Bearer JWT и возвращает payload токена.

    Ищет пользователя в БД по keycloak_id (= поле sub из JWT).
    Если пользователь ещё не синхронизирован — 401, нужно сначала вызвать POST /auth/sync.
    """
    payload = await verify_keycloak_token(credentials.credentials, redis)

    keycloak_id: str | None = payload.get("sub")
    if not keycloak_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT 'sub' claim is missing",
        )

    res = await db.execute(select(User).where(User.keycloak_id == keycloak_id))
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not synced. Call POST /api/v1/auth/sync first.",
        )

    # Добавляем наш внутренний UUID и объект пользователя в payload,
    # чтобы downstream-зависимости не делали лишний запрос в БД
    payload["internal_user_id"] = str(user.id)
    payload["_db_user"] = user
    return payload


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_role(role: str):
    """Проверяет наличие realm-роли у пользователя. Использовать как Depends(require_role("admin"))."""
    async def _check(user: CurrentUser) -> dict:
        roles: list[str] = user.get("realm_access", {}).get("roles", [])
        if role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return _check
