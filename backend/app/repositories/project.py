"""Repository: CRUD операции с проектами."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project


async def get_by_id(db: AsyncSession, project_id: UUID) -> Project | None:
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def list_by_user(db: AsyncSession, user_id: UUID) -> list[Project]:
    result = await db.execute(
        select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


async def create(db: AsyncSession, *, user_id: UUID, name: str, prompt: str, **kwargs) -> Project:
    project = Project(user_id=user_id, name=name, prompt=prompt, **kwargs)
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


async def update_status(db: AsyncSession, project_id: UUID, status: str) -> Project | None:
    project = await get_by_id(db, project_id)
    if project:
        project.status = status  # type: ignore[assignment]
        await db.flush()
    return project


async def delete(db: AsyncSession, project_id: UUID) -> bool:
    project = await get_by_id(db, project_id)
    if project:
        await db.delete(project)
        await db.flush()
        return True
    return False
