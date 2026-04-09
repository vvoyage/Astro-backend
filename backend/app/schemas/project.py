from pydantic import BaseModel, UUID4, computed_field, model_validator
from datetime import datetime
from typing import Optional

from app.core.config import settings

class ProjectBase(BaseModel):
    name: str  # название проекта

class ProjectCreate(ProjectBase):
    template_id: Optional[UUID4] = None  # ID шаблона (если используется)
    prompt: Optional[str] = None  # промпт (обязателен, если не указан template_id)

    @model_validator(mode='after')
    def check_prompt_or_template(self) -> 'ProjectCreate':
        if not self.template_id and not self.prompt:
            raise ValueError("Either template_id or prompt must be provided")
        return self

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    prompt: Optional[str] = None

    @model_validator(mode='after')
    def check_at_least_one(self) -> 'ProjectUpdate':
        if self.name is None and self.prompt is None:
            raise ValueError("At least one of name or prompt must be provided")
        if self.prompt is not None and not self.prompt.strip():
            raise ValueError("Prompt cannot be empty if provided")
        return self

class Project(ProjectBase):
    id: UUID4
    user_id: UUID4
    template_id: Optional[UUID4]
    prompt: str  # промпт всегда есть
    s3_path: str
    status: str
    created_at: datetime

    @computed_field
    @property
    def preview_url(self) -> Optional[str]:
        if not self.s3_path or self.s3_path == "pending":
            return None
        return f"{settings.MINIO_PUBLIC_URL}/astro-projects/{self.s3_path}/build/index.html"

    class Config:
        from_attributes = True

class ProjectPreview(BaseModel):
    project_id: UUID4
    path: str