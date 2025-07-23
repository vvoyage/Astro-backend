
from uuid import UUID, uuid4
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class Template(Base):
    __tablename__ = "templates"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    text_prompt: Mapped[str] = mapped_column(String, nullable=False)