from passlib.context import CryptContext
from typing import Optional

# Создаем контекст для хеширования паролей с использованием bcrypt
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12  # Количество раундов хеширования для безопасности
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие открытого пароля хешированному.
    
    Args:
        plain_password: Открытый пароль
        hashed_password: Хешированный пароль из базы данных
        
    Returns:
        bool: True если пароль верный, False если нет
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """
    Хеширует пароль.
    
    Args:
        password: Открытый пароль для хеширования
        
    Returns:
        str: Хешированный пароль
    """
    return pwd_context.hash(password)

def validate_password(password: str) -> tuple[bool, Optional[str]]:
    """
    Проверяет сложность пароля.
    
    Args:
        password: Пароль для проверки
        
    Returns:
        tuple[bool, Optional[str]]: (True, None) если пароль валидный,
                                   (False, error_message) если нет
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    return True, None