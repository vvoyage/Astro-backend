from pydantic import BaseModel, UUID4
from typing import Optional

class TemplateBase(BaseModel):
    name: str  # название шаблона
    text_prompt: str  # промпт для генерации

class TemplateCreate(TemplateBase):
    pass

class TemplateUpdate(TemplateBase):
    pass

class Template(TemplateBase):
    id: UUID4  # уникальный идентификатор шаблона

    class Config:
        from_attributes = True