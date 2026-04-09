"""Repository: CRUD операции с деплоями."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.deployment import Deployment


async def list_by_project(db: AsyncSession, project_id: UUID) -> list[Deployment]:
    result = await db.execute(
        select(Deployment)
        .where(Deployment.project_id == project_id)
        .order_by(Deployment.created_at.desc())
    )
    return list(result.scalars().all())


async def get_by_id(db: AsyncSession, deployment_id: UUID) -> Deployment | None:
    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession, *, project_id: UUID, provider: str, config: dict
) -> Deployment:
    deployment = Deployment(project_id=project_id, provider=provider, config=config)
    db.add(deployment)
    await db.flush()
    await db.refresh(deployment)
    return deployment


async def update_status(
    db: AsyncSession, deployment_id: UUID, *, status: str, deployment_url: str | None = None
) -> Deployment | None:
    deployment = await get_by_id(db, deployment_id)
    if deployment:
        deployment.status = status  # type: ignore[assignment]
        if deployment_url:
            deployment.deployment_url = deployment_url  # type: ignore[assignment]
        await db.flush()
    return deployment
