from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.db.models.user import User


async def get_current_active_user(
    payload: Annotated[dict, Depends(get_current_user)],
) -> User:
    """Возвращает User ORM-объект. Использует _db_user из get_current_user, без лишнего DB-запроса."""
    user: User = payload["_db_user"]
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return user
