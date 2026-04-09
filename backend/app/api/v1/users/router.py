"""Users API: получение и обновление профиля текущего пользователя."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.db.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


class UserUpdate(BaseModel):
    full_name: Optional[str] = None


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: CurrentUser,
    db: DbSession,
) -> User:
    """Возвращает профиль текущего пользователя."""
    db_user: User | None = user.get("_db_user")
    if db_user is None:
        from uuid import UUID
        res = await db.execute(select(User).where(User.id == UUID(user["internal_user_id"])))
        db_user = res.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    user: CurrentUser,
    db: DbSession,
) -> User:
    """Обновляет full_name текущего пользователя в PostgreSQL."""
    if body.full_name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    db_user: User | None = user.get("_db_user")
    if db_user is None:
        from uuid import UUID
        res = await db.execute(select(User).where(User.id == UUID(user["internal_user_id"])))
        db_user = res.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db_user.full_name = body.full_name  # type: ignore[assignment]
    await db.flush()
    await db.refresh(db_user)
    return db_user
