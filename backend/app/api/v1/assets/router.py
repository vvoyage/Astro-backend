"""Assets API: загрузка, список и удаление ассетов проекта из бакета astro-assets."""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.db.models.asset import Asset as AssetModel
from app.db.models.project import Project as ProjectModel
from app.schemas.asset import Asset
from app.services.storage import StorageService

router = APIRouter(prefix="/assets", tags=["assets"])


# ---------------------------------------------------------------------------
# Загрузка
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=Asset, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
    file: UploadFile = File(...),
) -> AssetModel:
    """Загружает файл в бакет astro-assets и регистрирует его в БД.

    Файл сохраняется по пути ``{user_id}/{project_id}/{filename}`` внутри бакета.
    s3_path и optimized_path указывают на один и тот же ключ (оптимизации пока нет).
    """
    user_id = UUID(user["internal_user_id"])
    await _get_owned_project(session, project_id, user_id)

    filename = file.filename or "upload"
    # Заменяем разделители пути, чтобы нельзя было выйти за пределы префикса
    filename = filename.replace("/", "_").replace("\\", "_")
    object_key = f"{user_id}/{project_id}/{filename}"

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    storage = StorageService()
    try:
        await storage.save_file("assets", object_key, data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading asset: {e}",
        )

    # Upsert: если файл с тем же путём уже зарегистрирован — вернуть существующую запись
    existing = await session.execute(
        select(AssetModel).where(AssetModel.s3_path == object_key)
    )
    asset = existing.scalar_one_or_none()
    if asset is None:
        asset = AssetModel(
            project_id=project_id,
            s3_path=object_key,
            optimized_path=object_key,
        )
        session.add(asset)
        await session.flush()
        await session.refresh(asset)
    return asset


# ---------------------------------------------------------------------------
# Список
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[Asset])
async def list_assets(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> List[AssetModel]:
    """Возвращает все ассеты проекта (проект должен принадлежать текущему пользователю)."""
    user_id = UUID(user["internal_user_id"])
    await _get_owned_project(session, project_id, user_id)

    result = await session.execute(
        select(AssetModel).where(AssetModel.project_id == project_id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Удаление
# ---------------------------------------------------------------------------

@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_asset(
    asset_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> None:
    """Удаляет ассет из MinIO и из базы данных."""
    user_id = UUID(user["internal_user_id"])

    result = await session.execute(
        select(AssetModel).where(AssetModel.id == asset_id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    # Проверяем, что ассет принадлежит проекту текущего пользователя
    await _get_owned_project(session, asset.project_id, user_id)

    storage = StorageService()
    try:
        bucket_name = storage.BUCKETS["assets"]
        await storage._delete_single_object(bucket_name, asset.s3_path)
    except Exception:
        pass  # best-effort: удаляем из БД даже если MinIO вернул ошибку

    await session.delete(asset)
    await session.flush()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _get_owned_project(session, project_id: UUID, user_id: UUID) -> ProjectModel:
    result = await session.execute(
        select(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.user_id == user_id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
