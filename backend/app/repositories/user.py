"""Repository: CRUD операции с пользователями в PostgreSQL."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User


async def get_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_by_keycloak_id(db: AsyncSession, keycloak_id: str) -> User | None:
    result = await db.execute(select(User).where(User.keycloak_id == keycloak_id))
    return result.scalar_one_or_none()


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, *, keycloak_id: str, email: str, username: str) -> User:
    user = User(keycloak_id=keycloak_id, email=email, username=username)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def upsert_from_token(
    db: AsyncSession, *, keycloak_id: str, email: str, username: str
) -> User:
    """Синхронизация пользователя из Keycloak — создать если нет, вернуть если есть."""
    user = await get_by_keycloak_id(db, keycloak_id)
    if user is None:
        user = await create(db, keycloak_id=keycloak_id, email=email, username=username)
    return user
