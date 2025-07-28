from pydantic import BaseModel, UUID4, model_validator
from datetime import datetime
from typing import Optional

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

class ProjectUpdate(ProjectBase):
    prompt: Optional[str] = None  # промпт можно обновлять

    @model_validator(mode='after')
    def check_prompt_not_empty(self) -> 'ProjectUpdate':
        if self.prompt is not None and not self.prompt.strip():
            raise ValueError("Prompt cannot be empty if provided")
        return self

class Project(ProjectBase):
    id: UUID4
    user_id: UUID4
    template_id: Optional[UUID4]
    prompt: str  # промпт всегда есть
    s3_path: str
    created_at: datetime

    class Config:
        from_attributes = True

class ProjectPreview(BaseModel):
    project_id: UUID4
    path: str