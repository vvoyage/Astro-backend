"""ORM модели — реэкспорт из app.db.models.

Это переходной слой: согласно STRUCTURE.md модели должны жить здесь,
но пока alembic настроен на app.db.models — оставляем там, реэкспортируем сюда.
TODO (Фаза 1): перенести модели сюда и обновить alembic env.py.
"""
from app.db.models.user import User
from app.db.models.project import Project
from app.db.models.template import Template
from app.db.models.snapshot import Snapshot
from app.db.models.deployment import Deployment

__all__ = ["User", "Project", "Template", "Snapshot", "Deployment"]
