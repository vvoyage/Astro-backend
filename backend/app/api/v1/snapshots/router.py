"""Snapshots API: список снапшотов проекта и восстановление версии файла."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.db.models.project import Project as ProjectModel
from app.db.models.snapshot import Snapshot as SnapshotModel
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
) -> RestoreResponse:
    """Восстанавливает файл проекта из снапшота и запускает пересборку.

    minio_path снапшота имеет вид:
        projects/{user_id}/{project_id}/snapshots/v{version}/{file_path}

    Файл копируется обратно в активный путь:
        projects/{user_id}/{project_id}/{file_path}
    """
    user_id = UUID(user["internal_user_id"])

    snapshot = await snapshot_repo.get_by_id(db, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    await _get_owned_project(db, snapshot.project_id, user_id)

    snap_dir_prefix = (
        f"projects/{user_id}/{snapshot.project_id}/snapshots/v{snapshot.version}/"
    )
    if not snapshot.minio_path.startswith(snap_dir_prefix):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine active path from snapshot minio_path",
        )
    relative_file_path = snapshot.minio_path[len(snap_dir_prefix):]
    active_path = f"projects/{user_id}/{snapshot.project_id}/{relative_file_path}"

    storage = StorageService()
    try:
        data = await storage.get_file("projects", snapshot.minio_path)
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

    from app.workers.tasks.build import run_build  # noqa: PLC0415

    run_build.delay(str(snapshot.project_id), str(user_id))

    return RestoreResponse(
        snapshot_id=snapshot_id,
        project_id=snapshot.project_id,
        file_path=relative_file_path,
        version=snapshot.version,
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
