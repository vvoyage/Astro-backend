from pydantic import BaseModel, UUID4, HttpUrl
from typing import Literal
from datetime import datetime
from enum import Enum

class ProviderType(str, Enum):
    VERCEL = "vercel"
    NETLIFY = "netlify"
    GITHUB_PAGES = "github_pages"

class DeploymentStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"

class DeploymentBase(BaseModel):
    provider: ProviderType
    domain: str
    status: DeploymentStatus

class DeploymentCreate(DeploymentBase):
    project_id: UUID4

class DeploymentUpdate(BaseModel):
    provider: ProviderType | None = None
    domain: str | None = None
    status: DeploymentStatus | None = None

class Deployment(DeploymentBase):
    id: UUID4
    project_id: UUID4

    class Config:
        from_attributes = True