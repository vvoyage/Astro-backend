import asyncio
import json
from io import BytesIO
from typing import List, Optional, Union

from loguru import logger
from minio import Minio

from app.core.config import settings

logger = logger.bind(context="minio")


class StorageService:
    """
    Сервис для работы с MinIO хранилищем.
    Управляет тремя бакетами:
    - astro-projects: файлы проектов пользователей
    - astro-templates: системные шаблоны проекта
    - astro-assets: используемые ассеты

    Все публичные async методы оборачивают синхронный minio-клиент
    через asyncio.to_thread() чтобы не блокировать event loop.
    """

    BUCKETS = {
        "projects": "astro-projects",
        "templates": "astro-templates",
        "assets": "astro-assets",
    }

    def __init__(self) -> None:
        logger.info("Initializing MinIO client with endpoint: {}", settings.MINIO_ENDPOINT)
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._initialize_buckets()

    # ------------------------------------------------------------------
    # Sync helpers (called via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _sync_initialize_buckets(self) -> None:
        for bucket_name in self.BUCKETS.values():
            try:
                if not self.client.bucket_exists(bucket_name):
                    logger.info("Creating bucket: {}", bucket_name)
                    self.client.make_bucket(bucket_name)
                    if bucket_name == self.BUCKETS["projects"]:
                        self._sync_set_public_policy(bucket_name)
                        logger.debug("Set public policy for bucket: {}", bucket_name)
            except Exception as e:
                logger.error("Error initializing bucket {}: {}", bucket_name, str(e))
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

    def _sync_get_object(self, bucket_name: str, object_name: str) -> bytes:
        response = self.client.get_object(bucket_name, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    # ------------------------------------------------------------------
    # Initialization (sync — called in __init__ before any async context)
    # ------------------------------------------------------------------

    def _initialize_buckets(self) -> None:
        self._sync_initialize_buckets()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

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
            logger.debug("Saving file {} to bucket {}", object_name, self.BUCKETS[bucket_type])
            raw: bytes = data if isinstance(data, bytes) else data.getvalue()
            await asyncio.to_thread(
                self._sync_put_object,
                self.BUCKETS[bucket_type],
                object_name,
                raw,
            )
            logger.info("Saved file {} to bucket {}", object_name, self.BUCKETS[bucket_type])
        except Exception as e:
            logger.error("Error saving file {} to bucket {}: {}", object_name, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error saving file to MinIO: {str(e)}")

    async def save_source_files(self, user_id: str, project_id: str, files: dict[str, str]) -> None:
        """
        Сохраняет сгенерированные исходники в MinIO.

        Args:
            user_id: ID пользователя
            project_id: ID проекта
            files: словарь {относительный_путь: содержимое_файла}
        """
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
            "Saved {} source files for project {}/{}", len(files), user_id, project_id
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
            logger.error("Error creating directory {} in bucket {}: {}", directory, self.BUCKETS[bucket_type], str(e))
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
            logger.error("Error deleting directory {} from bucket {}: {}", prefix, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error deleting directory from MinIO: {str(e)}")

    async def list_files(self, bucket_type: str, prefix: str) -> List[str]:
        if bucket_type not in self.BUCKETS:
            raise ValueError(f"Invalid bucket type: {bucket_type}")
        try:
            return await asyncio.to_thread(
                self._sync_list_objects, self.BUCKETS[bucket_type], prefix
            )
        except Exception as e:
            logger.error("Error listing files in bucket {}: {}", self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error listing files in MinIO: {str(e)}")

    async def get_file(self, bucket_type: str, object_name: str) -> Optional[bytes]:
        if bucket_type not in self.BUCKETS:
            raise ValueError(f"Invalid bucket type: {bucket_type}")
        try:
            return await asyncio.to_thread(
                self._sync_get_object, self.BUCKETS[bucket_type], object_name
            )
        except Exception as e:
            logger.error("Error reading file {} from bucket {}: {}", object_name, self.BUCKETS[bucket_type], str(e))
            raise Exception(f"Error reading file from MinIO: {str(e)}")