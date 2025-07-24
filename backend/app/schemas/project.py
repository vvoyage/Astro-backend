from pydantic import BaseModel, UUID4
from datetime import datetime
from typing import Optional

class ProjectBase(BaseModel):
    name: str  # название проекта
    s3_path: str  # путь к файлам проекта в S3

class ProjectCreate(ProjectBase):
    user_id: UUID4  # ID владельца проекта
    template_id: Optional[UUID4] = None  # ID шаблона (если используется)

class ProjectUpdate(ProjectBase):
    pass

class Project(ProjectBase):
    id: UUID4  # уникальный идентификатор проекта
    user_id: UUID4  # связь с пользователем
    template_id: Optional[UUID4]  # связь с шаблоном
    created_at: datetime  # время создания

    class Config:
        from_attributes = True