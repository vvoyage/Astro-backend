import sys
import os
from pathlib import Path

# Добавляем путь к корневой директории проекта в PYTHONPATH
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

from app.services.storage import StorageService
from app.services.queue import QueueService
from kubernetes import client, config
from app.core.config import settings


async def _check_connections():
    # Проверка MinIO
    storage = StorageService()
    try:
        await storage.list_files("projects", "test/")
        print("MinIO connection: OK")
    except Exception as e:
        print(f"MinIO connection failed: {e}")

    # Проверка RabbitMQ
    queue = QueueService()
    try:
        await queue.connect()
        print("RabbitMQ connection: OK")
    except Exception as e:
        print(f"RabbitMQ connection failed: {e}")

    # Проверка Kubernetes
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        v1.list_namespace()
        print("Kubernetes connection: OK")
    except Exception as e:
        print(f"Kubernetes connection failed: {e}")

# Запустить тест
import asyncio
if __name__ == "__main__":
    asyncio.run(_check_connections())