import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования HTTP запросов и добавления Request ID.
    
    Функции:
    - Генерация или извлечение Request ID из header X-Request-ID
    - Логирование входящих запросов
    - Логирование ответов с временем выполнения
    - Добавление Request ID в контекст всех логов в рамках запроса
    - Добавление Request ID в response headers
    """
    
    def __init__(self, app: ASGIApp, service_name: str = "unknown"):
        super().__init__(app)
        self.service_name = service_name
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Ленивая инициализация логгера (после setup_logging)
        from backend.logger import get_logger
        
        # Генерация или извлечение Request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Добавление Request ID в state запроса для доступа в endpoints
        request.state.request_id = request_id
        
        # Связывание Request ID с контекстом логгера
        log = get_logger(self.service_name).bind(request_id=request_id)
        
        # Запись начала обработки запроса
        start_time = time.time()
        
        # Логирование входящего запроса
        log.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params) if request.query_params else None,
            client_host=request.client.host if request.client else None,
        )
        
        try:
            # Обработка запроса
            response = await call_next(request)
            
            # Вычисление времени выполнения
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Логирование успешного ответа
            log.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            
            # Добавление Request ID в response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as exc:
            # Вычисление времени выполнения до ошибки
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Логирование ошибки
            log.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            
            # Пробрасывание исключения дальше для обработки FastAPI
            raise


def get_request_id(request: Request) -> str:
    """
    Получить Request ID из текущего запроса.
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        Request ID строка
    """
    return getattr(request.state, "request_id", "unknown")

