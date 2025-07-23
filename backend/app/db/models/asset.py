from uuid import UUID, uuid4
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base

class Asset(Base):
    __tablename__ = "assets"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    s3_path: Mapped[str] = mapped_column(String(255), nullable=False)
    optimized_path: Mapped[str] = mapped_column(String(255), nullable=False)

    # Отношения
    project = relationship("Project", back_populates="assets")