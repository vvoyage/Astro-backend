
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.database import Base

class Project(Base):
    __tablename__ = "projects"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    template_id: Mapped[UUID] = mapped_column(ForeignKey("templates.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_path: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Отношения
    user = relationship("User", back_populates="projects")
    template = relationship("Template")
    deployments = relationship("Deployment", back_populates="project")
    snapshots = relationship("Snapshot", back_populates="project")
    assets = relationship("Asset", back_populates="project")