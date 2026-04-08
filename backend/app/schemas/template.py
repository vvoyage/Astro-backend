from pydantic import BaseModel, UUID4, computed_field
from typing import Optional


class TemplateBase(BaseModel):
    name: str
    text_prompt: str
    slug: str
    description: Optional[str] = None
    is_active: bool = True


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(TemplateBase):
    pass


class Template(TemplateBase):
    id: UUID4

    @computed_field
    @property
    def prompt_hint(self) -> str:
        return self.text_prompt

    class Config:
        from_attributes = True
