from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security.jwt import create_access_token
from app.core.security.password import (
    get_password_hash,
    validate_password,
    verify_password
)
from app.db.database import get_async_session
from app.db.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserResponse
from .dependencies import get_current_active_user

# Схема для логина
class LoginData(BaseModel):
    email: str
    password: str

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={401: {"description": "Unauthorized"}}
)

@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)]
) -> User:
    """
    Регистрация нового пользователя.
    """
    # Проверяем существование пользователя
    query = select(User).where(User.email == user_data.email)
    result = await session.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Валидация пароля
    is_valid, error_message = validate_password(user_data.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    
    # Создаем нового пользователя
    db_user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name
    )
    
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    
    return db_user

@router.post("/login", response_model=Token)
async def login(
    login_data: LoginData,
    session: Annotated[AsyncSession, Depends(get_async_session)]
) -> Token:
    """
    Вход в систему
    """
    # Проверяем учетные данные пользователя
    query = select(User).where(User.email == login_data.email)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Создаем access token
    access_token = create_access_token(
        subject=user.email,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(access_token=access_token)

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    """
    Получить данные текущего пользователя.
    """
    return current_user

@router.get("/protected-example")
async def protected_route(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    """
    Пример защищенного маршрута.
    """
    return {
        "message": f"Hello, {current_user.full_name}!",
        "email": current_user.email
    }