from typing import Optional
from pydantic import BaseModel, UUID4, computed_field

from app.core.config import settings


class AssetBase(BaseModel):
    project_id: UUID4
    s3_path: str
    optimized_path: str


class AssetCreate(AssetBase):
    pass


class AssetUpdate(AssetBase):
    pass


class Asset(AssetBase):
    id: UUID4

    @computed_field
    @property
    def url(self) -> str:
        return f"{settings.MINIO_PUBLIC_URL}/astro-assets/{self.s3_path}"

    @computed_field
    @property
    def filename(self) -> str:
        """Last segment of s3_path — the original sanitised filename."""
        return self.s3_path.rsplit("/", 1)[-1]

    class Config:
        from_attributes = True
