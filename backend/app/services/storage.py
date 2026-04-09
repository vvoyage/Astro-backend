import asyncio
import json
from io import BytesIO
from typing import List, Optional, Union

from loguru import logger
from minio import Minio
from minio.commonconfig import CopySource

from app.core.config import settings

logger = logger.bind(context="minio")


class StorageService:
    """
    Работа с MinIO: три бакета — проекты, шаблоны, ассеты.
    Синхронный клиент minio оборачивается в asyncio.to_thread(), чтобы не блокировать event loop.
    """

    BUCKETS = {
        "projects": "astro-projects",
        "templates": "astro-templates",
        "assets": "astro-assets",
    }

    def __init__(self) -> None:
        logger.info("Инициализация MinIO клиента, endpoint: {}", settings.MINIO_ENDPOINT)
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._initialize_buckets()

    PUBLIC_BUCKETS = {"projects", "assets"}

    def _sync_initialize_buckets(self) -> None:
        for bucket_type, bucket_name in self.BUCKETS.items():
            try:
                if not self.client.bucket_exists(bucket_name):
                    logger.info("Создание бакета: {}", bucket_name)
                    self.client.make_bucket(bucket_name)
                # Политика публичного чтения применяется при каждом старте — в том числе
                # для бакетов, созданных до того, как политика была добавлена.
                if bucket_type in self.PUBLIC_BUCKETS:
                    self._sync_set_public_policy(bucket_name)
                    logger.debug("Установлена публичная политика для бакета: {}", bucket_name)
            except Exception as e:
                logger.error("Ошибка инициализации бакета {}: {}", bucket_name, str(e))
                raise

    def _sync_set_public_policy(self, bucket_name: str) -> None:
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                }
            ],
        }
        self.client.set_bucket_policy(bucket_name, json.dumps(policy))

    def _sync_put_object(self, bucket_name: str, object_name: str, data: bytes) -> None:
        self.client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=BytesIO(data),
            length=len(data),
        )

    def _sync_list_objects(self, bucket_name: str, prefix: str, recursive: bool = True) -> List[str]:
        objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=recursive)
        return [obj.object_name for obj in objects]

    def _sync_remove_object(self, bucket_name: str, object_name: str) -> None:
        self.client.remove_object(bucket_name, object_name)

    async def _delete_single_object(self, bucket_name: str, object_name: str) -> None:
        """Удаляет один объект по реальному имени бакета и ключу."""
        await asyncio.to_thread(self._sync_remove_object, bucket_name, object_name)

    def _sync_copy_object(self, bucket_name: str, src_object: str, dst_object: str) -> None:
        self.client.copy_object(bucket_name, dst_object, CopySource(bucket_name, src_object))

    def _sync_get_object(self, bucket_name: str, object_name: str) -> bytes:
        response = self.client.get_object(bucket_name, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def _initialize_buckets(self) -> None:
        self._sync_initialize_buckets()

    async def create_project_structure(self, user_id: str, project_id: str = "000") -> None:
        base_path = f"projects/{user_id}/{project_id}"
        for directory in [f"{base_path}/src", f"{base_path}/build", f"{base_path}/snapshots"]:
            await self.create_directory("projects", directory)

    async def cleanup_default_project(self, user_id: str) -> None:
        prefix = f"projects/{user_id}/000/"
        await self.delete_directory("projects", prefix)

    async def save_file(
        self,
        bucket_type: str,
        object_name: str,
        data: Union[BytesIO, bytes],
        length: Optional[int] = None,
    ) -> None:
        if bucket_type not in self.BUCKETS:
            raise ValueError(f"Invalid bucket type: {bucket_type}")

        try:
            logger.debug("Сохранение файла {} в бакет {}", object_name, self.BUCKETS[bucket_type])
            raw: bytes = data if isinstance(data, bytes) else data.getvalue()
            await asyncio.to_thread(
                self._sync_put_object,
                self.BUCKETS[bucket_type],
                object_name,
                raw,
            )
            logger.info("Файл {} сохранён в бакет {}", object_name, self.BUCKETS[bucket_type])
        except Exception as e:
            logger.error("Ошибка сохранения файла {} в бакет {}: {}", object_name, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error saving file to MinIO: {str(e)}")

    async def save_source_files(self, user_id: str, project_id: str, files: dict[str, str]) -> None:
        """Сохраняет сгенерированные файлы в MinIO параллельно. files — {путь: контент}."""
        tasks = [
            self.save_file(
                "projects",
                f"projects/{user_id}/{project_id}/{path.lstrip('/')}",
                content.encode("utf-8"),
            )
            for path, content in files.items()
        ]
        await asyncio.gather(*tasks)
        logger.info(
            "Сохранено {} исходных файлов для проекта {}/{}", len(files), user_id, project_id
        )

    async def create_directory(self, bucket_type: str, directory: str) -> None:
        if bucket_type not in self.BUCKETS:
            raise ValueError(f"Invalid bucket type: {bucket_type}")
        try:
            dir_key = directory if directory.endswith("/") else directory + "/"
            await asyncio.to_thread(
                self._sync_put_object,
                self.BUCKETS[bucket_type],
                dir_key,
                b"",
            )
        except Exception as e:
            logger.error("Ошибка создания директории {} в бакете {}: {}", directory, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error creating directory in MinIO: {str(e)}")

    async def delete_directory(self, bucket_type: str, prefix: str) -> None:
        if bucket_type not in self.BUCKETS:
            raise ValueError(f"Invalid bucket type: {bucket_type}")
        try:
            bucket_name = self.BUCKETS[bucket_type]
            object_names: List[str] = await asyncio.to_thread(
                self._sync_list_objects, bucket_name, prefix
            )
            for name in object_names:
                await asyncio.to_thread(self._sync_remove_object, bucket_name, name)
        except Exception as e:
            logger.error("Ошибка удаления директории {} из бакета {}: {}", prefix, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error deleting directory from MinIO: {str(e)}")

    async def list_files(self, bucket_type: str, prefix: str) -> List[str]:
        if bucket_type not in self.BUCKETS:
            raise ValueError(f"Invalid bucket type: {bucket_type}")
        try:
            return await asyncio.to_thread(
                self._sync_list_objects, self.BUCKETS[bucket_type], prefix
            )
        except Exception as e:
            logger.error("Ошибка получения списка файлов в бакете {}: {}", self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error listing files in MinIO: {str(e)}")

    async def copy_directory(self, bucket_type: str, src_prefix: str, dst_prefix: str) -> None:
        """Копирует все объекты из src_prefix в dst_prefix внутри одного бакета."""
        if bucket_type not in self.BUCKETS:
            raise ValueError(f"Invalid bucket type: {bucket_type}")
        bucket_name = self.BUCKETS[bucket_type]
        src_prefix = src_prefix.rstrip("/") + "/"
        dst_prefix = dst_prefix.rstrip("/") + "/"
        try:
            object_names: List[str] = await asyncio.to_thread(
                self._sync_list_objects, bucket_name, src_prefix
            )
            for src_obj in object_names:
                dst_obj = dst_prefix + src_obj[len(src_prefix):]
                await asyncio.to_thread(self._sync_copy_object, bucket_name, src_obj, dst_obj)
            logger.info("Скопировано {} объектов из {} в {}", len(object_names), src_prefix, dst_prefix)
        except Exception as e:
            logger.error("Ошибка копирования директории {} -> {}: {}", src_prefix, dst_prefix, str(e))
            raise Exception(f"Error copying directory in MinIO: {str(e)}")

    async def get_file(self, bucket_type: str, object_name: str) -> Optional[bytes]:
        if bucket_type not in self.BUCKETS:
            raise ValueError(f"Invalid bucket type: {bucket_type}")
        try:
            return await asyncio.to_thread(
                self._sync_get_object, self.BUCKETS[bucket_type], object_name
            )
        except Exception as e:
            logger.error("Ошибка чтения файла {} из бакета {}: {}", object_name, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error reading file from MinIO: {str(e)}")