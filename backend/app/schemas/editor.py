"""Pydantic-схемы для эндпоинта /editor."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ElementInfo(BaseModel):
    editable_id: str
    file_path: str
    element_html: str


class EditElementRequest(BaseModel):
    project_id: str
    element: ElementInfo
    instruction: str = Field(..., min_length=1, max_length=2000)
    ai_model: str = Field(default="gpt-5.4")


class EditElementResponse(BaseModel):
    task_id: str
    project_id: str
    file_path: str
    status: str = "queued"


class GetFileRequest(BaseModel):
    project_id: str
    file_path: str


class UpdateFileRequest(BaseModel):
    project_id: str
    file_path: str
    content: str
