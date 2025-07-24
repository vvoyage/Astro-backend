from uuid import UUID, uuid4
from sqlalchemy import String, ForeignKey, Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from enum import Enum

class ProviderType(str, Enum):
    VERCEL = "vercel"
    NETLIFY = "netlify"
    GITHUB_PAGES = "github_pages"

class DeploymentStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"

class Deployment(Base):
    __tablename__ = "deployments"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    provider: Mapped[ProviderType] = mapped_column(SQLAlchemyEnum(ProviderType), nullable=False)
    domain: Mapped[str] = mapped_column(String(255))
    status: Mapped[DeploymentStatus] = mapped_column(SQLAlchemyEnum(DeploymentStatus), nullable=False)

    # Отношения
    project = relationship("Project", back_populates="deployments")