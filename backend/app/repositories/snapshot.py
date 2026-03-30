"""Repository: CRUD операции со снапшотами версий проектов."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot import Snapshot


async def list_by_project(db: AsyncSession, project_id: UUID) -> list[Snapshot]:
    result = await db.execute(
        select(Snapshot)
        .where(Snapshot.project_id == project_id)
        .order_by(Snapshot.version.desc())
    )
    return list(result.scalars().all())


async def get_by_id(db: AsyncSession, snapshot_id: UUID) -> Snapshot | None:
    result = await db.execute(select(Snapshot).where(Snapshot.id == snapshot_id))
    return result.scalar_one_or_none()


async def get_latest_version(db: AsyncSession, project_id: UUID) -> int:
    snapshots = await list_by_project(db, project_id)
    return snapshots[0].version if snapshots else 0


async def create(
    db: AsyncSession, *, project_id: UUID, version: int, minio_path: str, description: str = ""
) -> Snapshot:
    snapshot = Snapshot(
        project_id=project_id,
        version=version,
        minio_path=minio_path,
        description=description,
    )
    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)
    return snapshot
