from .user import User
from .project import Project
from .asset import Asset
from .deployment import Deployment
from .snapshot import Snapshot
from .template import Template

# Для правильной инициализации всех моделей
__all__ = [
    "User",
    "Project",
    "Asset",
    "Deployment",
    "Snapshot",
    "Template"
]