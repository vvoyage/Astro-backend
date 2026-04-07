"""Unit-тесты для GET /snapshots/{project_id} и POST /snapshots/{id}/restore.

Запуск:
    cd backend
    pytest tests/test_snapshots_api.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _user(uid: str | None = None) -> dict:
    uid = uid or str(uuid4())
    return {"internal_user_id": uid}


def _make_storage(get_file_return: bytes | None = b"<h1>old content</h1>"):
    import app.services.storage as _storage_mod
    from app.services.storage import StorageService

    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    with patch.object(_storage_mod, "Minio", return_value=mock_client):
        svc = StorageService()

    svc.get_file = AsyncMock(return_value=get_file_return)
    svc.save_file = AsyncMock()
    return svc


def _make_snapshot(
    project_id: UUID | None = None,
    version: int = 1,
    user_id: str | None = None,
    file_path: str = "src/index.astro",
) -> MagicMock:
    """Создаёт мок Snapshot с валидным minio_path."""
    snap = MagicMock()
    snap.id = uuid4()
    snap.project_id = project_id or uuid4()
    snap.version = version
    snap.description = "Before edit: test prompt"
    uid = user_id or str(uuid4())
    snap.minio_path = (
        f"projects/{uid}/{snap.project_id}/snapshots/v{version}/{file_path}"
    )
    return snap


def _db_with_project() -> AsyncMock:
    """DB-сессия, в которой запрос проекта возвращает мок (проект найден)."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _db_no_project() -> AsyncMock:
    """DB-сессия, в которой проект не найден."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


# ===========================================================================
# GET /snapshots/{project_id}
# ===========================================================================

@pytest.mark.asyncio
class TestListSnapshots:

    async def test_returns_snapshots_for_owned_project(self):
        from app.api.v1.snapshots.router import list_snapshots

        uid = str(uuid4())
        project_id = uuid4()
        snap1 = _make_snapshot(project_id=project_id, version=2, user_id=uid)
        snap2 = _make_snapshot(project_id=project_id, version=1, user_id=uid)

        with patch(
            "app.api.v1.snapshots.router.snapshot_repo.list_by_project",
            new=AsyncMock(return_value=[snap1, snap2]),
        ):
            result = await list_snapshots(
                project_id=project_id, user=_user(uid), db=_db_with_project()
            )

        assert result == [snap1, snap2]

    async def test_returns_empty_list_when_no_snapshots(self):
        from app.api.v1.snapshots.router import list_snapshots

        with patch(
            "app.api.v1.snapshots.router.snapshot_repo.list_by_project",
            new=AsyncMock(return_value=[]),
        ):
            result = await list_snapshots(
                project_id=uuid4(), user=_user(), db=_db_with_project()
            )

        assert result == []

    async def test_raises_404_when_project_not_owned(self):
        from fastapi import HTTPException
        from app.api.v1.snapshots.router import list_snapshots

        with pytest.raises(HTTPException) as exc_info:
            await list_snapshots(
                project_id=uuid4(), user=_user(), db=_db_no_project()
            )

        assert exc_info.value.status_code == 404
        assert "Project not found" in exc_info.value.detail

    async def test_calls_list_by_project_with_correct_id(self):
        from app.api.v1.snapshots.router import list_snapshots

        project_id = uuid4()
        mock_list = AsyncMock(return_value=[])

        with patch("app.api.v1.snapshots.router.snapshot_repo.list_by_project", new=mock_list):
            await list_snapshots(
                project_id=project_id, user=_user(), db=_db_with_project()
            )

        mock_list.assert_called_once()
        assert mock_list.call_args[0][1] == project_id


# ===========================================================================
# POST /snapshots/{snapshot_id}/restore
# ===========================================================================

@pytest.mark.asyncio
class TestRestoreSnapshot:

    async def test_raises_404_when_snapshot_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.snapshots.router import restore_snapshot

        with patch(
            "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await restore_snapshot(
                    snapshot_id=uuid4(), user=_user(), db=_db_with_project()
                )

        assert exc_info.value.status_code == 404
        assert "Snapshot not found" in exc_info.value.detail

    async def test_raises_404_when_project_not_owned(self):
        from fastapi import HTTPException
        from app.api.v1.snapshots.router import restore_snapshot

        uid = str(uuid4())
        snap = _make_snapshot(user_id=uid)

        with patch(
            "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
            new=AsyncMock(return_value=snap),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await restore_snapshot(
                    snapshot_id=snap.id, user=_user(uid), db=_db_no_project()
                )

        assert exc_info.value.status_code == 404
        assert "Project not found" in exc_info.value.detail

    async def test_raises_400_when_minio_path_format_invalid(self):
        """Снапшот с кривым minio_path → 400, не падаем с 500."""
        from fastapi import HTTPException
        from app.api.v1.snapshots.router import restore_snapshot

        uid = str(uuid4())
        snap = _make_snapshot(user_id=uid, version=1)
        snap.minio_path = "some/unexpected/path/file.astro"  # не по конвенции

        with (
            patch(
                "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
                new=AsyncMock(return_value=snap),
            ),
            patch(
                "app.api.v1.snapshots.router.StorageService",
                return_value=_make_storage(),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await restore_snapshot(
                    snapshot_id=snap.id, user=_user(uid), db=_db_with_project()
                )

        assert exc_info.value.status_code == 400

    async def test_reads_from_correct_snapshot_path(self):
        from app.api.v1.snapshots.router import restore_snapshot

        uid = str(uuid4())
        project_id = uuid4()
        snap = _make_snapshot(project_id=project_id, version=3, user_id=uid)
        storage = _make_storage(get_file_return=b"snapshot content")

        with (
            patch(
                "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
                new=AsyncMock(return_value=snap),
            ),
            patch("app.api.v1.snapshots.router.StorageService", return_value=storage),
            patch("app.workers.tasks.build.run_build"),
        ):
            await restore_snapshot(snapshot_id=snap.id, user=_user(uid), db=_db_with_project())

        storage.get_file.assert_called_once_with("projects", snap.minio_path)

    async def test_writes_to_active_file_path(self):
        from app.api.v1.snapshots.router import restore_snapshot

        uid = str(uuid4())
        project_id = uuid4()
        file_path = "src/pages/index.astro"
        snap = _make_snapshot(project_id=project_id, version=2, user_id=uid, file_path=file_path)
        content = b"<h1>restored</h1>"
        storage = _make_storage(get_file_return=content)

        with (
            patch(
                "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
                new=AsyncMock(return_value=snap),
            ),
            patch("app.api.v1.snapshots.router.StorageService", return_value=storage),
            patch("app.workers.tasks.build.run_build"),
        ):
            await restore_snapshot(snapshot_id=snap.id, user=_user(uid), db=_db_with_project())

        expected_active_path = f"projects/{uid}/{project_id}/{file_path}"
        storage.save_file.assert_called_once_with("projects", expected_active_path, content)

    async def test_returns_correct_response_fields(self):
        from app.api.v1.snapshots.router import restore_snapshot

        uid = str(uuid4())
        project_id = uuid4()
        file_path = "src/components/Hero.astro"
        snap = _make_snapshot(project_id=project_id, version=5, user_id=uid, file_path=file_path)
        storage = _make_storage(get_file_return=b"code")

        with (
            patch(
                "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
                new=AsyncMock(return_value=snap),
            ),
            patch("app.api.v1.snapshots.router.StorageService", return_value=storage),
            patch("app.workers.tasks.build.run_build"),
        ):
            result = await restore_snapshot(
                snapshot_id=snap.id, user=_user(uid), db=_db_with_project()
            )

        assert result.snapshot_id == snap.id
        assert result.project_id == project_id
        assert result.file_path == file_path
        assert result.version == 5
        assert result.status == "restoring"

    async def test_triggers_build_with_correct_args(self):
        from app.api.v1.snapshots.router import restore_snapshot

        uid = str(uuid4())
        project_id = uuid4()
        snap = _make_snapshot(project_id=project_id, version=1, user_id=uid)
        storage = _make_storage(get_file_return=b"data")

        with (
            patch(
                "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
                new=AsyncMock(return_value=snap),
            ),
            patch("app.api.v1.snapshots.router.StorageService", return_value=storage),
            patch("app.workers.tasks.build.run_build") as mock_run_build,
        ):
            await restore_snapshot(snapshot_id=snap.id, user=_user(uid), db=_db_with_project())

        mock_run_build.delay.assert_called_once_with(str(project_id), uid)

    async def test_raises_500_when_storage_read_fails(self):
        from fastapi import HTTPException
        from app.api.v1.snapshots.router import restore_snapshot

        uid = str(uuid4())
        snap = _make_snapshot(user_id=uid)
        storage = _make_storage()
        storage.get_file = AsyncMock(side_effect=Exception("MinIO connection refused"))

        with (
            patch(
                "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
                new=AsyncMock(return_value=snap),
            ),
            patch("app.api.v1.snapshots.router.StorageService", return_value=storage),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await restore_snapshot(
                    snapshot_id=snap.id, user=_user(uid), db=_db_with_project()
                )

        assert exc_info.value.status_code == 500
        assert "MinIO connection refused" in exc_info.value.detail

    async def test_raises_500_when_storage_write_fails(self):
        from fastapi import HTTPException
        from app.api.v1.snapshots.router import restore_snapshot

        uid = str(uuid4())
        snap = _make_snapshot(user_id=uid)
        storage = _make_storage(get_file_return=b"data")
        storage.save_file = AsyncMock(side_effect=Exception("MinIO write error"))

        with (
            patch(
                "app.api.v1.snapshots.router.snapshot_repo.get_by_id",
                new=AsyncMock(return_value=snap),
            ),
            patch("app.api.v1.snapshots.router.StorageService", return_value=storage),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await restore_snapshot(
                    snapshot_id=snap.id, user=_user(uid), db=_db_with_project()
                )

        assert exc_info.value.status_code == 500
        assert "MinIO write error" in exc_info.value.detail
