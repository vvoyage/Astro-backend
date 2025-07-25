from pydantic import BaseModel

class Token(BaseModel):
    """Схема ответа с токеном доступа"""
    access_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    """Схема данных внутри токена"""
    sub: str | None = None
    exp: int | None = None