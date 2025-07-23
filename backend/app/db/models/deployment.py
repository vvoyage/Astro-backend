from uuid import UUID, uuid4
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base

class Deployment(Base):
    __tablename__ = "deployments"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    domain: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # Отношения
    project = relationship("Project", back_populates="deployments")