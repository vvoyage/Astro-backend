from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SnapshotResponse(BaseModel):
    id: UUID
    project_id: UUID
    version: int
    minio_path: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RestoreResponse(BaseModel):
    snapshot_id: UUID
    project_id: UUID
    file_path: str
    version: int
    status: str
