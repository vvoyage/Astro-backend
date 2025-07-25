from datetime import datetime, timedelta
from typing import Any, Optional

from jose import JWTError, jwt
from fastapi import HTTPException, status

from app.core.config import settings

class TokenError(Exception):
    """Базовое исключение для ошибок связанных с токенами"""
    pass

def create_access_token(
    subject: str | Any,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Создает JWT access token.
    
    Args:
        subject: Идентификатор пользователя (email)
        expires_delta: Время жизни токена
        
    Returns:
        str: JWT токен
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode = {"exp": expire, "sub": str(subject)}
    
    try:
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        return encoded_jwt
    except JWTError as e:
        raise TokenError(f"Failed to create token: {str(e)}")

def verify_token(token: str) -> dict[str, Any]:
    """
    Проверяет JWT токен.
    
    Args:
        token: JWT токен для проверки
        
    Returns:
        dict: Декодированные данные токена
        
    Raises:
        HTTPException: Если токен недействителен
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )