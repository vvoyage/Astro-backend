from loguru import logger
import sys
import os

# Создаем директорию для логов если её нет
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Настройка логгера
def setup_logging():
    # Удаляем стандартный handler
    logger.remove()
    
    # Добавляем форматированный вывод в консоль
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # Логи MinIO
    logger.add(
        "logs/minio.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        filter=lambda record: "minio" in record["extra"],
        rotation="100 MB",
        retention="30 days",
        level="DEBUG"
    )
    
    # Логи Kubernetes
    logger.add(
        "logs/kubernetes.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        filter=lambda record: "kubernetes" in record["extra"],
        rotation="100 MB",
        retention="30 days",
        level="DEBUG"
    )

    return logger
