"""Pydantic-схемы для эндпоинта /generation."""
from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class GenerationStage(str, Enum):
    queued = "queued"
    optimizer = "optimizer"
    architect = "architect"
    code_generator = "code_generator"
    saving = "saving"
    building = "building"
    done = "done"
    error = "error"


class GenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=5000)
    ai_model: str = Field(default="gpt-5.4-mini")
    template_slug: str | None = None


class GenerationStatus(BaseModel):
    project_id: UUID
    stage: GenerationStage
    progress: int = Field(ge=0, le=100)
    message: str = ""
    error: str | None = None
