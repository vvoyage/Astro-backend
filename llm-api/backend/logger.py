import logging
import sys
import os
import structlog


def setup_logging():
    """
    Настройка структурированного логирования с помощью structlog.
    
    Конфигурация:
    - Формат: JSON
    - Вывод: stdout
    - Уровень: из переменной окружения LOG_LEVEL (по умолчанию INFO)
    - Timestamp в ISO 8601 формате с UTC
    """
    
    # Получение уровня логирования из переменной окружения
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    
    if log_level not in valid_levels:
        print(f"Warning: Invalid LOG_LEVEL '{log_level}', using INFO. Valid levels: {', '.join(valid_levels)}", file=sys.stderr)
        log_level = "INFO"
    
    # Проверка на включение JSON формата (по умолчанию включен)
    use_json = os.getenv("LOG_JSON", "true").lower() in ("true", "1", "yes")
    
    # Настройка стандартного logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )
    
    # Процессоры для structlog
    processors = [
        # Добавление имени логгера
        structlog.stdlib.add_log_level,
        # Добавление timestamp в ISO 8601
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Добавление информации о стеке при исключениях
        structlog.processors.StackInfoRenderer(),
        # Форматирование исключений
        structlog.processors.format_exc_info,
    ]
    
    # Выбор рендерера в зависимости от настройки
    if use_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    # Конфигурация structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(service_name: str = "llm-api"):
    """
    Получить логгер с предустановленным контекстом сервиса.
    
    Args:
        service_name: Имя микросервиса для идентификации в логах
        
    Returns:
        Логгер с привязанным контекстом сервиса
    """
    return structlog.get_logger().bind(service=service_name)

