from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict

class UserBase(BaseModel):
    """Базовая схема пользователя"""
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    """Схема для создания пользователя"""
    password: str

class UserUpdate(UserBase):
    """Схема для обновления пользователя"""
    password: Optional[str] = None

class UserInDB(UserBase):
    """Схема пользователя в БД"""
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Новая конфигурация для Pydantic v2
    model_config = ConfigDict(
        from_attributes=True,  # Заменяет orm_mode=True
        json_encoders={
            UUID: str
        }
    )

class UserResponse(UserInDB):
    """Схема ответа с данными пользователя"""
    pass  # Наследуем все поля из UserInDB, кроме hashed_password 