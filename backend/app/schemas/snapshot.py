from pydantic import BaseModel, UUID4
from datetime import datetime

class SnapshotBase(BaseModel):
    project_id: UUID4  # связь с проектом
    version_id: str  # идентификатор версии
    s3_path: str  # путь к снэпшоту в S3

class SnapshotCreate(SnapshotBase):
    pass

class SnapshotUpdate(SnapshotBase):
    pass

class Snapshot(SnapshotBase):
    id: UUID4  # уникальный идентификатор снэпшота
    created_at: datetime  # время создания

    class Config:
        from_attributes = True