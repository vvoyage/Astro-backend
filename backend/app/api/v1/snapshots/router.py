"""Snapshots API: список снапшотов проекта и восстановление версии файла."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession, RedisClient
from app.db.models.project import Project as ProjectModel
from app.db.models.snapshot import Snapshot as SnapshotModel
from app.repositories import project as project_repo
from app.repositories import snapshot as snapshot_repo
from app.schemas.snapshot import RestoreResponse, SnapshotResponse
from app.services.storage import StorageService

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/{project_id}", response_model=list[SnapshotResponse])
async def list_snapshots(
    project_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[SnapshotModel]:
    """Все снапшоты проекта, от новых к старым."""
    user_id = UUID(user["internal_user_id"])
    await _get_owned_project(db, project_id, user_id)
    return await snapshot_repo.list_by_project(db, project_id)


@router.post("/{snapshot_id}/restore", response_model=RestoreResponse)
async def restore_snapshot(
    snapshot_id: UUID,
    user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
) -> RestoreResponse:
    """Восстанавливает ПОЛНОЕ состояние проекта на момент версии target и запускает пересборку.

    Для каждого файла, который существовал в версии <= target, берётся
    его состояние из ближайшего снапшота <= target.  Это гарантирует, что
    файлы, изменённые в более поздних версиях (например, all-files правка),
    тоже будут корректно откачены.

    minio_path снапшота имеет вид:
        projects/{user_id}/{project_id}/snapshots/v{version}/{file_path}
    """
    user_id = UUID(user["internal_user_id"])

    snapshot = await snapshot_repo.get_by_id(db, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    await _get_owned_project(db, snapshot.project_id, user_id)

    version = snapshot.version
    snap_base = f"projects/{user_id}/{snapshot.project_id}/snapshots/"

    # Все снапшоты версий <= target, от новых к старым.
    # Для каждого файла берём первый встреченный (т.е. с наибольшей версией <= target).
    all_prior_snapshots = await snapshot_repo.list_up_to_version(db, snapshot.project_id, version)

    # Строим карту: относительный путь файла → снапшот, который надо восстановить.
    file_to_snap: dict[str, SnapshotModel] = {}
    for snap in all_prior_snapshots:
        if not snap.minio_path.startswith(snap_base):
            continue
        after_base = snap.minio_path[len(snap_base):]  # "v{n}/{rel_path}"
        slash = after_base.index("/")
        rel_path = after_base[slash + 1:]              # "{rel_path}"
        if rel_path and rel_path not in file_to_snap:
            file_to_snap[rel_path] = snap

    if not file_to_snap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No snapshots found for this version or earlier",
        )

    storage = StorageService()
    first_relative_path = next(iter(file_to_snap))

    for rel_path, snap in file_to_snap.items():
        active_path = f"projects/{user_id}/{snap.project_id}/src/{rel_path}"

        try:
            data = await storage.get_file("projects", snap.minio_path)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error reading snapshot from storage: {exc}",
            ) from exc

        try:
            await storage.save_file("projects", active_path, data)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error writing restored file: {exc}",
            ) from exc

    await project_repo.set_active_snapshot_version(db, snapshot.project_id, version)
    await db.commit()

    await redis.set(
        f"generation:{snapshot.project_id}:status",
        json.dumps({"stage": "queued", "progress": 0}),
        ex=86400,
    )

    from app.workers.tasks.build import run_build  # noqa: PLC0415

    run_build.delay(str(snapshot.project_id), str(user_id))

    return RestoreResponse(
        snapshot_id=snapshot_id,
        project_id=snapshot.project_id,
        file_path=first_relative_path,
        version=version,
        status="restoring",
    )


async def _get_owned_project(db: DbSession, project_id: UUID, user_id: UUID) -> ProjectModel:
    result = await db.execute(
        select(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.user_id == user_id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
