"""Unit-тесты для:
  - POST /assets/upload
  - GET  /assets/
  - DELETE /assets/{id}
  - GET  /projects/{id}/status

Запуск:
    cd backend
    pytest tests/test_assets_and_status_api.py -v
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# fastapi.responses не заглушен в conftest — нужен для импорта projects/router
_fr = MagicMock()
_fr.StreamingResponse = MagicMock
sys.modules.setdefault("fastapi.responses", _fr)


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _user(uid: UUID | None = None) -> dict:
    uid = uid or uuid4()
    return {"internal_user_id": str(uid)}


def _project(
    user_id: UUID | None = None,
    s3_path: str | None = None,
    status: str = "ready",
) -> MagicMock:
    uid = user_id or uuid4()
    p = MagicMock()
    p.id = uuid4()
    p.user_id = uid
    p.name = "Test Project"
    p.s3_path = s3_path if s3_path is not None else f"projects/{uid}/{p.id}"
    p.status = status
    p.template_id = None
    p.created_at = MagicMock()
    return p


def _asset(project_id: UUID | None = None, s3_path: str | None = None) -> MagicMock:
    a = MagicMock()
    a.id = uuid4()
    a.project_id = project_id or uuid4()
    a.s3_path = s3_path or f"{uuid4()}/{uuid4()}/image.png"
    a.optimized_path = a.s3_path
    return a


def _upload_file(filename: str = "image.png", data: bytes = b"fake image data") -> MagicMock:
    f = MagicMock()
    f.filename = filename
    f.read = AsyncMock(return_value=data)
    return f


def _make_storage() -> MagicMock:
    """StorageService с замоканным Minio клиентом."""
    import app.services.storage as _storage_mod
    from app.services.storage import StorageService

    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    with patch.object(_storage_mod, "Minio", return_value=mock_client):
        svc = StorageService()

    svc.save_file = AsyncMock()
    svc._delete_single_object = AsyncMock()
    return svc


def _mock_asset_cls() -> MagicMock:
    """Возвращает MagicMock-класс для патчинга AssetModel.

    SQLAlchemy ORM заглушен в conftest, поэтому реальный конструктор
    AssetModel() не принимает аргументы. Патчим его на MagicMock.
    """
    created = MagicMock()
    cls = MagicMock(return_value=created)
    cls._created_instance = created  # удобно для проверки в тестах
    return cls


def _session_seq(*scalar_values) -> AsyncMock:
    """
    Сессия, execute() которой последовательно возвращает scalar_one_or_none()
    из переданных значений.
    """
    session = AsyncMock()
    results = []
    for val in scalar_values:
        r = MagicMock()
        r.scalar_one_or_none.return_value = val
        results.append(r)

    call_count = 0

    async def _execute(_query):
        nonlocal call_count
        idx = min(call_count, len(results) - 1)
        call_count += 1
        return results[idx]

    session.execute = AsyncMock(side_effect=_execute)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


def _session_for_list(project: MagicMock | None, assets: list) -> AsyncMock:
    """
    Сессия для list_assets:
    1-й execute → scalar_one_or_none (project)
    2-й execute → scalars().all() (assets)
    """
    session = AsyncMock()
    r1 = MagicMock()
    r1.scalar_one_or_none.return_value = project
    r2 = MagicMock()
    r2.scalars.return_value.all.return_value = assets

    call_count = 0

    async def _execute(_query):
        nonlocal call_count
        result = r1 if call_count == 0 else r2
        call_count += 1
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


# ===========================================================================
# POST /assets/upload
# ===========================================================================

@pytest.mark.asyncio
class TestUploadAsset:

    async def test_saves_file_to_minio(self):
        from app.api.v1.assets.router import upload_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        storage = _make_storage()
        asset_cls = _mock_asset_cls()
        session = _session_seq(proj, None)  # project found, no existing asset

        with (
            patch("app.api.v1.assets.router.StorageService", return_value=storage),
            patch("app.api.v1.assets.router.AssetModel", asset_cls),
        ):
            await upload_asset(
                project_id=proj.id,
                user=_user(uid),
                session=session,
                file=_upload_file("photo.jpg", b"jpeg data"),
            )

        storage.save_file.assert_called_once()
        assert storage.save_file.call_args[0][0] == "assets"
        assert storage.save_file.call_args[0][2] == b"jpeg data"

    async def test_object_key_contains_user_project_filename(self):
        from app.api.v1.assets.router import upload_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        storage = _make_storage()
        asset_cls = _mock_asset_cls()
        session = _session_seq(proj, None)

        with (
            patch("app.api.v1.assets.router.StorageService", return_value=storage),
            patch("app.api.v1.assets.router.AssetModel", asset_cls),
        ):
            await upload_asset(
                project_id=proj.id,
                user=_user(uid),
                session=session,
                file=_upload_file("logo.png"),
            )

        key = storage.save_file.call_args[0][1]
        assert str(uid) in key
        assert str(proj.id) in key
        assert "logo.png" in key

    async def test_sanitises_filename_path_separators(self):
        """../../evil/path.png не должен содержать / в части filename."""
        from app.api.v1.assets.router import upload_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        storage = _make_storage()
        asset_cls = _mock_asset_cls()
        session = _session_seq(proj, None)

        with (
            patch("app.api.v1.assets.router.StorageService", return_value=storage),
            patch("app.api.v1.assets.router.AssetModel", asset_cls),
        ):
            await upload_asset(
                project_id=proj.id,
                user=_user(uid),
                session=session,
                file=_upload_file("../../evil/path.png"),
            )

        key = storage.save_file.call_args[0][1]
        # После двух сегментов prefix (uid/proj_id/) filename не должен содержать /
        filename_part = key.split("/", 2)[-1]
        assert "/" not in filename_part
        assert "\\" not in filename_part

    async def test_raises_404_when_project_not_owned(self):
        from fastapi import HTTPException
        from app.api.v1.assets.router import upload_asset

        session = _session_seq(None)  # project not found

        with pytest.raises(HTTPException) as exc_info:
            await upload_asset(
                project_id=uuid4(),
                user=_user(),
                session=session,
                file=_upload_file(),
            )

        assert exc_info.value.status_code == 404

    async def test_raises_400_on_empty_file(self):
        from fastapi import HTTPException
        from app.api.v1.assets.router import upload_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        storage = _make_storage()
        session = _session_seq(proj, None)

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            with pytest.raises(HTTPException) as exc_info:
                await upload_asset(
                    project_id=proj.id,
                    user=_user(uid),
                    session=session,
                    file=_upload_file(data=b""),
                )

        assert exc_info.value.status_code == 400

    async def test_raises_500_when_minio_fails(self):
        from fastapi import HTTPException
        from app.api.v1.assets.router import upload_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        storage = _make_storage()
        storage.save_file = AsyncMock(side_effect=Exception("connection refused"))
        session = _session_seq(proj, None)

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            with pytest.raises(HTTPException) as exc_info:
                await upload_asset(
                    project_id=proj.id,
                    user=_user(uid),
                    session=session,
                    file=_upload_file(),
                )

        assert exc_info.value.status_code == 500
        assert "connection refused" in exc_info.value.detail

    async def test_upsert_returns_existing_asset_no_db_insert(self):
        """Повторная загрузка того же файла — session.add не вызывается."""
        from app.api.v1.assets.router import upload_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        existing = _asset(project_id=proj.id)
        storage = _make_storage()
        session = _session_seq(proj, existing)  # second execute returns existing asset

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            result = await upload_asset(
                project_id=proj.id,
                user=_user(uid),
                session=session,
                file=_upload_file(),
            )

        session.add.assert_not_called()
        assert result is existing

    async def test_new_asset_added_to_db(self):
        """Новый файл → session.add + flush + refresh."""
        from app.api.v1.assets.router import upload_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        storage = _make_storage()
        asset_cls = _mock_asset_cls()
        session = _session_seq(proj, None)

        with (
            patch("app.api.v1.assets.router.StorageService", return_value=storage),
            patch("app.api.v1.assets.router.AssetModel", asset_cls),
        ):
            await upload_asset(
                project_id=proj.id,
                user=_user(uid),
                session=session,
                file=_upload_file(),
            )

        session.add.assert_called_once_with(asset_cls._created_instance)
        session.flush.assert_called_once()
        session.refresh.assert_called_once()

    async def test_minio_write_happens_before_db_insert(self):
        """MinIO save_file должен вызваться до session.add."""
        from app.api.v1.assets.router import upload_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        storage = _make_storage()
        call_order: list[str] = []
        storage.save_file = AsyncMock(side_effect=lambda *a: call_order.append("minio"))
        asset_cls = _mock_asset_cls()
        session = _session_seq(proj, None)
        original_add = MagicMock(side_effect=lambda a: call_order.append("db_add"))
        session.add = original_add

        with (
            patch("app.api.v1.assets.router.StorageService", return_value=storage),
            patch("app.api.v1.assets.router.AssetModel", asset_cls),
        ):
            await upload_asset(
                project_id=proj.id,
                user=_user(uid),
                session=session,
                file=_upload_file(),
            )

        assert call_order.index("minio") < call_order.index("db_add")


# ===========================================================================
# GET /assets/
# ===========================================================================

@pytest.mark.asyncio
class TestListAssets:

    async def test_returns_assets_for_owned_project(self):
        from app.api.v1.assets.router import list_assets

        uid = uuid4()
        proj = _project(user_id=uid)
        assets = [_asset(proj.id), _asset(proj.id)]
        session = _session_for_list(proj, assets)

        result = await list_assets(
            project_id=proj.id, user=_user(uid), session=session
        )

        assert result == assets

    async def test_returns_empty_list_when_no_assets(self):
        from app.api.v1.assets.router import list_assets

        uid = uuid4()
        proj = _project(user_id=uid)
        session = _session_for_list(proj, [])

        result = await list_assets(
            project_id=proj.id, user=_user(uid), session=session
        )

        assert result == []

    async def test_raises_404_when_project_not_owned(self):
        from fastapi import HTTPException
        from app.api.v1.assets.router import list_assets

        session = _session_for_list(None, [])

        with pytest.raises(HTTPException) as exc_info:
            await list_assets(
                project_id=uuid4(), user=_user(), session=session
            )

        assert exc_info.value.status_code == 404

    async def test_queries_by_project_id(self):
        """Второй execute должен быть вызван (запрос ассетов)."""
        from app.api.v1.assets.router import list_assets

        uid = uuid4()
        proj = _project(user_id=uid)
        session = _session_for_list(proj, [])

        await list_assets(project_id=proj.id, user=_user(uid), session=session)

        assert session.execute.call_count == 2


# ===========================================================================
# DELETE /assets/{id}
# ===========================================================================

@pytest.mark.asyncio
class TestDeleteAsset:

    async def test_deletes_from_minio_and_db(self):
        from app.api.v1.assets.router import delete_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        asset = _asset(project_id=proj.id)
        storage = _make_storage()
        session = _session_seq(asset, proj)

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            await delete_asset(asset_id=asset.id, user=_user(uid), session=session)

        storage._delete_single_object.assert_called_once()
        session.delete.assert_called_once_with(asset)
        session.flush.assert_called_once()

    async def test_uses_correct_bucket_name(self):
        from app.api.v1.assets.router import delete_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        asset = _asset(project_id=proj.id, s3_path="u/p/file.png")
        storage = _make_storage()
        session = _session_seq(asset, proj)

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            await delete_asset(asset_id=asset.id, user=_user(uid), session=session)

        bucket, key = storage._delete_single_object.call_args[0]
        assert bucket == "astro-assets"
        assert key == "u/p/file.png"

    async def test_raises_404_when_asset_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.assets.router import delete_asset

        session = _session_seq(None)
        storage = _make_storage()

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            with pytest.raises(HTTPException) as exc_info:
                await delete_asset(asset_id=uuid4(), user=_user(), session=session)

        assert exc_info.value.status_code == 404
        assert "Asset not found" in exc_info.value.detail

    async def test_raises_404_when_project_not_owned(self):
        from fastapi import HTTPException
        from app.api.v1.assets.router import delete_asset

        uid = uuid4()
        asset = _asset()
        storage = _make_storage()
        session = _session_seq(asset, None)  # asset found, project not owned

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            with pytest.raises(HTTPException) as exc_info:
                await delete_asset(asset_id=asset.id, user=_user(uid), session=session)

        assert exc_info.value.status_code == 404

    async def test_db_delete_proceeds_if_minio_fails(self):
        """Ошибка MinIO не прерывает удаление из БД (best-effort)."""
        from app.api.v1.assets.router import delete_asset

        uid = uuid4()
        proj = _project(user_id=uid)
        asset = _asset(project_id=proj.id)
        storage = _make_storage()
        storage._delete_single_object = AsyncMock(side_effect=Exception("MinIO down"))
        session = _session_seq(asset, proj)

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            await delete_asset(asset_id=asset.id, user=_user(uid), session=session)  # не кидает

        session.delete.assert_called_once_with(asset)

    async def test_minio_not_called_if_asset_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.assets.router import delete_asset

        storage = _make_storage()
        session = _session_seq(None)

        with patch("app.api.v1.assets.router.StorageService", return_value=storage):
            with pytest.raises(HTTPException):
                await delete_asset(asset_id=uuid4(), user=_user(), session=session)

        storage._delete_single_object.assert_not_called()


# ===========================================================================
# GET /projects/{id}/status
# ===========================================================================

@pytest.mark.asyncio
class TestGetProjectStatus:

    async def test_returns_status_and_preview_url(self):
        from app.api.v1.projects.router import get_project_status

        uid = uuid4()
        proj = _project(user_id=uid, status="ready")
        session = _session_seq(proj)

        result = await get_project_status(
            project_id=proj.id, user=_user(uid), session=session
        )

        assert result.status == "ready"
        assert result.preview_url is not None
        assert "astro-projects" in result.preview_url
        assert proj.s3_path in result.preview_url

    async def test_preview_url_ends_with_index_html(self):
        from app.api.v1.projects.router import get_project_status

        uid = uuid4()
        proj = _project(user_id=uid, status="ready")
        session = _session_seq(proj)

        result = await get_project_status(
            project_id=proj.id, user=_user(uid), session=session
        )

        assert result.preview_url.endswith("/build/index.html")

    async def test_preview_url_is_none_when_s3_path_is_pending(self):
        from app.api.v1.projects.router import get_project_status

        uid = uuid4()
        proj = _project(user_id=uid, s3_path="pending", status="queued")
        session = _session_seq(proj)

        result = await get_project_status(
            project_id=proj.id, user=_user(uid), session=session
        )

        assert result.status == "queued"
        assert result.preview_url is None

    async def test_preview_url_is_none_when_s3_path_empty(self):
        from app.api.v1.projects.router import get_project_status

        uid = uuid4()
        proj = _project(user_id=uid, s3_path="", status="generating")
        session = _session_seq(proj)

        result = await get_project_status(
            project_id=proj.id, user=_user(uid), session=session
        )

        assert result.preview_url is None

    async def test_raises_404_when_project_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import get_project_status

        session = _session_seq(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_project_status(
                project_id=uuid4(), user=_user(), session=session
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.parametrize("st", ["queued", "generating", "building", "ready", "failed"])
    async def test_returns_correct_status_for_each_state(self, st: str):
        from app.api.v1.projects.router import get_project_status

        uid = uuid4()
        proj = _project(user_id=uid, status=st)
        session = _session_seq(proj)

        result = await get_project_status(
            project_id=proj.id, user=_user(uid), session=session
        )

        assert result.status == st

    async def test_status_contains_only_status_and_preview_url(self):
        from app.api.v1.projects.router import get_project_status, ProjectStatus

        uid = uuid4()
        proj = _project(user_id=uid)
        session = _session_seq(proj)

        result = await get_project_status(
            project_id=proj.id, user=_user(uid), session=session
        )

        assert isinstance(result, ProjectStatus)
        assert hasattr(result, "status")
        assert hasattr(result, "preview_url")


# ===========================================================================
# Схема Asset (computed fields)
# ===========================================================================

class TestAssetSchema:

    def test_url_computed_from_s3_path(self):
        from app.schemas.asset import Asset

        proj_id = uuid4()
        s3_path = f"{uuid4()}/{proj_id}/logo.png"

        asset = Asset(
            id=uuid4(),
            project_id=proj_id,
            s3_path=s3_path,
            optimized_path=s3_path,
        )

        assert s3_path in asset.url
        assert "astro-assets" in asset.url
        assert asset.url.startswith("http")

    def test_filename_extracted_correctly(self):
        from app.schemas.asset import Asset

        proj_id = uuid4()
        s3_path = f"{uuid4()}/{proj_id}/my-photo.jpg"

        asset = Asset(
            id=uuid4(),
            project_id=proj_id,
            s3_path=s3_path,
            optimized_path=s3_path,
        )

        assert asset.filename == "my-photo.jpg"

    def test_filename_for_simple_path(self):
        from app.schemas.asset import Asset

        proj_id = uuid4()
        s3_path = "banner.webp"

        asset = Asset(
            id=uuid4(),
            project_id=proj_id,
            s3_path=s3_path,
            optimized_path=s3_path,
        )

        assert asset.filename == "banner.webp"

    def test_url_contains_minio_public_url(self):
        """URL должен включать MINIO_PUBLIC_URL из settings."""
        from app.schemas.asset import Asset
        from app.core.config import settings

        proj_id = uuid4()
        s3_path = f"u/p/file.png"
        asset = Asset(
            id=uuid4(), project_id=proj_id, s3_path=s3_path, optimized_path=s3_path
        )

        assert asset.url.startswith(settings.MINIO_PUBLIC_URL)
