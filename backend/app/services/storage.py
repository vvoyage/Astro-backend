from minio import Minio
from app.core.config import settings
from loguru import logger
import os
import json
from typing import List, Optional, Union
from io import BytesIO

# Создаем логгер с контекстом minio
logger = logger.bind(context="minio")

class StorageService:
    """
    Сервис для работы с MinIO хранилищем.
    Управляет тремя бакетами:
    - astro-projects: файлы проектов пользователей
    - astro-templates: системные шаблоны проекта
    - astro-assets: используемые ассеты
    """
    
    BUCKETS = {
        "projects": "astro-projects",
        "templates": "astro-templates",
        "assets": "astro-assets"
    }

    def __init__(self):
        logger.info("Initializing MinIO client with endpoint: {}", settings.MINIO_ENDPOINT)
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        
        # Создаем бакеты при инициализации если они не существуют
        self._initialize_buckets()

    def _initialize_buckets(self):
        """Инициализация всех необходимых бакетов"""
        for bucket_name in self.BUCKETS.values():
            try:
                if not self.client.bucket_exists(bucket_name):
                    logger.info("Creating bucket: {}", bucket_name)
                    self.client.make_bucket(bucket_name)
                    # Устанавливаем публичный доступ для превью проектов
                    if bucket_name == self.BUCKETS["projects"]:
                        self._set_public_policy(bucket_name)
                        logger.debug("Set public policy for bucket: {}", bucket_name)
            except Exception as e:
                logger.error("Error initializing bucket {}: {}", bucket_name, str(e))
                raise

    def _set_public_policy(self, bucket_name: str):
        """Устанавливает публичный доступ на чтение для бакета"""
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                }
            ]
        }
        self.client.set_bucket_policy(bucket_name, json.dumps(policy))

    async def create_project_structure(self, user_id: str, project_id: str = "000") -> None:
        """
        Создает структуру проекта в MinIO:
        projects/
          {user_id}/
            {project_id}/
              src/         # Исходные файлы Astro
              build/       # Собранные статические файлы
              snapshots/   # Снимки истории (до 10 версий)
        """
        base_path = f"projects/{user_id}/{project_id}"
        directories = [
            f"{base_path}/src",
            f"{base_path}/build",
            f"{base_path}/snapshots"
        ]
        
        for directory in directories:
            await self.create_directory("projects", directory)

    async def cleanup_default_project(self, user_id: str) -> None:
        """Очищает временный проект с id='000'"""
        prefix = f"projects/{user_id}/000/"
        await self.delete_directory("projects", prefix)

    async def save_file(self, bucket_type: str, object_name: str, data: Union[BytesIO, bytes], length: Optional[int] = None) -> None:
        """
        Сохраняет файл в указанный бакет
        
        Args:
            bucket_type: тип бакета ("projects", "templates", "assets")
            object_name: путь к файлу в бакете
            data: содержимое файла (BytesIO или bytes)
            length: длина данных (обязательна для BytesIO)
        """
        if bucket_type not in self.BUCKETS:
            logger.error("Invalid bucket type: {}", bucket_type)
            raise ValueError(f"Invalid bucket type: {bucket_type}")
            
        try:
            logger.debug("Saving file {} to bucket {}", object_name, self.BUCKETS[bucket_type])
            if isinstance(data, bytes):
                # Если переданы байты, создаем BytesIO
                from io import BytesIO
                file_data = BytesIO(data)
                data_length = len(data)
            else:
                # Если передан BytesIO, используем как есть
                file_data = data
                data_length = length if length is not None else len(data.getvalue())
            
            self.client.put_object(
                bucket_name=self.BUCKETS[bucket_type],
                object_name=object_name,
                data=file_data,
                length=data_length
            )
            logger.info("Successfully saved file {} to bucket {}", object_name, self.BUCKETS[bucket_type])
        except Exception as e:
            logger.error("Error saving file {} to bucket {}: {}", object_name, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error saving file to MinIO: {str(e)}")

    async def create_directory(self, bucket_type: str, directory: str) -> None:
        """Создает директорию (пустой файл с / на конце)"""
        if bucket_type not in self.BUCKETS:
            logger.error("Invalid bucket type: {}", bucket_type)
            raise ValueError(f"Invalid bucket type: {bucket_type}")
            
        try:
            # Добавляем слеш в конец если его нет
            if not directory.endswith('/'):
                directory += '/'
                
            # Создаем пустой объект с именем, заканчивающимся на слеш
            self.client.put_object(
                bucket_name=self.BUCKETS[bucket_type],
                object_name=directory,  # само имя директории со слешем
                data=BytesIO(b''),
                length=0
            )
        except Exception as e:
            logger.error("Error creating directory {} in bucket {}: {}", directory, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error creating directory in MinIO: {str(e)}")

    async def delete_directory(self, bucket_type: str, prefix: str) -> None:
        """Удаляет директорию и все её содержимое"""
        if bucket_type not in self.BUCKETS:
            logger.error("Invalid bucket type: {}", bucket_type)
            raise ValueError(f"Invalid bucket type: {bucket_type}")
            
        try:
            objects = self.client.list_objects(self.BUCKETS[bucket_type], prefix=prefix, recursive=True)
            for obj in objects:
                self.client.remove_object(self.BUCKETS[bucket_type], obj.object_name)
        except Exception as e:
            logger.error("Error deleting directory {} from bucket {}: {}", prefix, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error deleting directory from MinIO: {str(e)}")

    async def list_files(self, bucket_type: str, prefix: str) -> List[str]:
        """Получает список файлов в директории"""
        if bucket_type not in self.BUCKETS:
            logger.error("Invalid bucket type: {}", bucket_type)
            raise ValueError(f"Invalid bucket type: {bucket_type}")
            
        try:
            objects = self.client.list_objects(self.BUCKETS[bucket_type], prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except Exception as e:
            logger.error("Error listing files in bucket {}: {}", self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error listing files in MinIO: {str(e)}")

    async def get_file(self, bucket_type: str, object_name: str) -> Optional[bytes]:
        """Получает содержимое файла"""
        if bucket_type not in self.BUCKETS:
            logger.error("Invalid bucket type: {}", bucket_type)
            raise ValueError(f"Invalid bucket type: {bucket_type}")
            
        try:
            data = self.client.get_object(self.BUCKETS[bucket_type], object_name)
            return data.read()
        except Exception as e:
            logger.error("Error reading file {} from bucket {}: {}", object_name, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error reading file from MinIO: {str(e)}")