"""Legacy JWT helpers — будут удалены после полной интеграции Keycloak (Блок 2)."""
import os
from datetime import datetime, timedelta
from typing import Any, Optional

from jose import JWTError, jwt
from fastapi import HTTPException, status

_SECRET_KEY = os.environ.get("SECRET_KEY", "")
_ALGORITHM = os.environ.get("ALGORITHM", "HS256")
_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


class TokenError(Exception):
    pass


def create_access_token(
    subject: str | Any,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {"exp": expire, "sub": str(subject)}
    try:
        return jwt.encode(to_encode, _SECRET_KEY, algorithm=_ALGORITHM)
    except JWTError as e:
        raise TokenError(f"Failed to create token: {str(e)}")


def verify_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )