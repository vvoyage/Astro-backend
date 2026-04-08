import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from redis.asyncio import Redis
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_redis
from app.core.security.keycloak import verify_keycloak_token
from app.core.security.keycloak_admin import create_keycloak_user, delete_keycloak_user
from app.core.security.password import validate_password
from app.db.database import get_async_session
from app.db.models.asset import Asset
from app.db.models.deployment import Deployment
from app.db.models.project import Project
from app.db.models.snapshot import Snapshot
from app.db.models.user import User
from app.schemas.user import UserResponse
from .dependencies import get_current_active_user

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str = ""
    last_name: str = ""


class RegisterResponse(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    message: str = "Registration successful. You can now log in via Keycloak."


class SyncResponse(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    created: bool


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={401: {"description": "Unauthorized"}},
)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> RegisterResponse:
    """Регистрация нового пользователя.

    Создаёт пользователя в Keycloak и сразу синхронизирует запись в PostgreSQL.
    После регистрации пользователь логинится через astro-frontend (OIDC).
    """
    is_valid, err = validate_password(data.password)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)

    # Создаём в Keycloak (409 если email занят, 503 если Keycloak недоступен)
    keycloak_id = await create_keycloak_user(
        email=data.email,
        password=data.password,
        first_name=data.first_name,
        last_name=data.last_name,
    )

    # Синхронизируем в PostgreSQL
    full_name = " ".join(filter(None, [data.first_name, data.last_name])) or None
    try:
        user = User(
            email=data.email,
            keycloak_id=keycloak_id,
            full_name=full_name,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        # Email уже есть в Postgres. Keycloak-аккаунт только что создан,
        # откатываем его чтобы не было дубля, и сообщаем пользователю.
        await session.rollback()
        await delete_keycloak_user(keycloak_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    except Exception:
        await session.rollback()
        await delete_keycloak_user(keycloak_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user record",
        )

    return RegisterResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


# ---------------------------------------------------------------------------
# Эндпоинты Keycloak
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Данные текущего аутентифицированного пользователя (из Keycloak JWT)."""
    return current_user


@router.post("/sync", response_model=SyncResponse)
async def sync_keycloak_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> SyncResponse:
    """Создать или обновить запись пользователя в PostgreSQL на основе Keycloak JWT.

    Нужен при первом входе через внешний IdP (например, Google SSO в будущем),
    или для обновления данных профиля (имя, email) из Keycloak.

    Claims из JWT:
    - ``sub``            — Keycloak UUID (keycloak_id)
    - ``email``          — адрес электронной почты
    - ``name``           — полное имя (или given_name + family_name)
    - ``email_verified`` — флаг верификации email
    """
    payload = await verify_keycloak_token(credentials.credentials, redis)

    keycloak_id: str | None = payload.get("sub")
    email: str | None = payload.get("email")
    if not keycloak_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JWT must contain 'sub' and 'email' claims",
        )

    full_name: str | None = payload.get("name") or (
        " ".join(filter(None, [payload.get("given_name"), payload.get("family_name")])) or None
    )
    email_verified: bool = bool(payload.get("email_verified", False))

    result = await session.execute(select(User).where(User.keycloak_id == keycloak_id))
    user = result.scalar_one_or_none()

    if user is None:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    created = user is None

    if created:
        user = User(
            email=email,
            keycloak_id=keycloak_id,
            full_name=full_name,
            email_verified=email_verified,
            is_active=True,
        )
        session.add(user)
    else:
        user.keycloak_id = keycloak_id
        user.email = email
        if full_name:
            user.full_name = full_name
        user.email_verified = email_verified

    await session.commit()
    await session.refresh(user)

    return SyncResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        created=created,
    )


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _purge_user_from_db(session: AsyncSession, user: User) -> None:
    """Удалить пользователя и все его данные из PostgreSQL.

    Порядок: assets → snapshots → deployments → projects → user,
    чтобы не нарушать FK-ограничения (ondelete не задан в моделях).
    """
    project_ids_result = await session.execute(
        select(Project.id).where(Project.user_id == user.id)
    )
    project_ids = [row[0] for row in project_ids_result.all()]

    if project_ids:
        await session.execute(sql_delete(Asset).where(Asset.project_id.in_(project_ids)))
        await session.execute(sql_delete(Snapshot).where(Snapshot.project_id.in_(project_ids)))
        await session.execute(sql_delete(Deployment).where(Deployment.project_id.in_(project_ids)))
        await session.execute(sql_delete(Project).where(Project.id.in_(project_ids)))

    await session.delete(user)
    await session.commit()


# ---------------------------------------------------------------------------
# Самоудаление
# ---------------------------------------------------------------------------

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Удалить собственный аккаунт.

    Сначала удаляет пользователя из Keycloak (инвалидирует все сессии),
    затем каскадно удаляет все данные из PostgreSQL.
    """
    keycloak_id = current_user.keycloak_id

    # Keycloak-удаление первым: если оно упадёт — PG остаётся нетронутым.
    if keycloak_id:
        await delete_keycloak_user(keycloak_id)

    try:
        await _purge_user_from_db(session, current_user)
    except Exception:
        logger.exception(
            "Failed to purge user %s from DB after Keycloak deletion", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account removed from Keycloak but DB cleanup failed",
        )
