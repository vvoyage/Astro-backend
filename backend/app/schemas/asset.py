from pydantic import BaseModel, UUID4

class AssetBase(BaseModel):
    project_id: UUID4  # связь с проектом
    s3_path: str  # оригинальный путь в S3
    optimized_path: str  # путь к оптимизированной версии

class AssetCreate(AssetBase):
    pass

class AssetUpdate(AssetBase):
    pass

class Asset(AssetBase):
    id: UUID4  # уникальный идентификатор ассета

    class Config:
        from_attributes = True