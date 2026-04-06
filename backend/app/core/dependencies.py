"""Dependency Injection фабрики для FastAPI Depends()."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security.jwt import verify_token
from app.db.database import get_async_session
from app.db.models.user import User

_bearer = HTTPBearer(auto_error=False)


def _user_claims(user_id: UUID) -> dict:
    return {
        "sub": str(user_id),
        "realm_access": {"roles": ["user"]},
    }


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
    """Возвращает singleton async Redis-клиент."""
    if _redis_client is None:
        raise RuntimeError("Redis не инициализирован. Вызовите init_redis() при старте приложения.")
    return _redis_client


RedisClient = Annotated[Redis, Depends(get_redis)]


# ---------------------------------------------------------------------------
# Current user (JWT или dev-заголовок)
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_dev_user_id: str | None = Header(default=None, alias="X-Dev-User-Id"),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Пользователь из Bearer JWT (sub = email или UUID) либо в DEBUG без токена — X-Dev-User-Id (UUID существующего User)."""
    if credentials is not None and credentials.credentials:
        payload = verify_token(credentials.credentials)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        user: User | None = None
        try:
            uid = UUID(str(sub))
        except ValueError:
            uid = None
        if uid is not None:
            res = await db.execute(select(User).where(User.id == uid))
            user = res.scalar_one_or_none()
        if user is None:
            res = await db.execute(select(User).where(User.email == str(sub)))
            user = res.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return _user_claims(user.id)

    if settings.DEBUG and x_dev_user_id:
        try:
            uid = UUID(x_dev_user_id.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Dev-User-Id must be a valid UUID",
            ) from exc
        res = await db.execute(select(User).where(User.id == uid))
        user = res.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No user with this id (dev mode)",
            )
        return _user_claims(user.id)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_role(role: str):
    """Dependency: проверяет что у пользователя есть нужная роль."""
    async def _check(user: CurrentUser) -> dict:
        roles: list[str] = user.get("realm_access", {}).get("roles", [])
        if role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return _check
