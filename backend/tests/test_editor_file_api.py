"""Unit-тесты для GET /file и PUT /file в api/v1/editor/router.py.

Запуск:
    cd backend
    pytest tests/test_editor_file_api.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные фабрики 
# ---------------------------------------------------------------------------

def _make_storage(get_file_return: bytes | None = b"<h1>Hello</h1>"):
    """StorageService с замоканным Minio и заданным get_file."""
    import app.services.storage as _storage_mod
    from app.services.storage import StorageService

    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    with patch.object(_storage_mod, "Minio", return_value=mock_client):
        svc = StorageService()

    svc.get_file = AsyncMock(return_value=get_file_return)
    svc.save_file = AsyncMock()
    return svc


def _user(uid: str | None = None) -> dict:
    uid = uid or str(uuid4())
    return {"internal_user_id": uid}


def _update_file_body(project_id: str, file_path: str = "src/index.astro", content: str = "<h1>New</h1>"):
    body = MagicMock()
    body.project_id = project_id
    body.file_path = file_path
    body.content = content
    return body


def _db_session(latest_version: int = 2) -> AsyncMock:
    """AsyncMock сессии; snapshot_repo.get_latest_version заменяется отдельно."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


# ===========================================================================
# GET /file
# ===========================================================================

@pytest.mark.asyncio
class TestGetFileCode:

    async def test_returns_content_when_file_exists(self):
        from app.api.v1.editor.router import get_file_code

        user = _user()
        project_id = str(uuid4())
        storage = _make_storage(get_file_return=b"const x = 1;")

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            result = await get_file_code(
                project_id=project_id,
                file_path="src/index.astro",
                user=user,
            )

        assert result["content"] == "const x = 1;"
        assert result["project_id"] == project_id
        assert result["file_path"] == "src/index.astro"

    async def test_raises_404_when_file_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.editor.router import get_file_code

        storage = _make_storage(get_file_return=None)

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            with pytest.raises(HTTPException) as exc_info:
                await get_file_code(
                    project_id=str(uuid4()),
                    file_path="src/missing.astro",
                    user=_user(),
                )

        assert exc_info.value.status_code == 404

    async def test_constructs_correct_minio_path(self):
        from app.api.v1.editor.router import get_file_code

        uid = str(uuid4())
        project_id = str(uuid4())
        storage = _make_storage(get_file_return=b"code")

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            await get_file_code(
                project_id=project_id,
                file_path="src/pages/index.astro",
                user=_user(uid),
            )

        storage.get_file.assert_called_once_with(
            "projects",
            f"projects/{uid}/{project_id}/src/pages/index.astro",
        )

    async def test_strips_leading_slash_from_file_path(self):
        from app.api.v1.editor.router import get_file_code

        uid = str(uuid4())
        project_id = str(uuid4())
        storage = _make_storage(get_file_return=b"code")

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            await get_file_code(
                project_id=project_id,
                file_path="/src/index.astro",
                user=_user(uid),
            )

        called_path = storage.get_file.call_args[0][1]
        assert "//" not in called_path
        assert called_path.startswith("projects/")


# ===========================================================================
# PUT /file
# ===========================================================================

@pytest.mark.asyncio
class TestUpdateFileCode:

    async def test_saves_new_content_to_minio(self):
        from app.api.v1.editor.router import update_file_code

        uid = str(uuid4())
        project_id = str(uuid4())
        storage = _make_storage(get_file_return=None)  # файла нет → нет снапшота
        db = _db_session()
        body = _update_file_body(project_id, content="<h1>Updated</h1>")

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            result = await update_file_code(body=body, db=db, user=_user(uid))

        storage.save_file.assert_called_once()
        saved_content = storage.save_file.call_args[0][2]
        assert saved_content == b"<h1>Updated</h1>"
        assert result["status"] == "saved"

    async def test_returns_correct_fields(self):
        from app.api.v1.editor.router import update_file_code

        project_id = str(uuid4())
        storage = _make_storage(get_file_return=None)
        body = _update_file_body(project_id, file_path="src/about.astro")

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            result = await update_file_code(body=body, db=_db_session(), user=_user())

        assert result["project_id"] == project_id
        assert result["file_path"] == "src/about.astro"
        assert result["status"] == "saved"

    async def test_creates_snapshot_when_file_exists(self):
        from app.api.v1.editor.router import update_file_code

        uid = str(uuid4())
        project_id = str(uuid4())
        existing_content = b"<h1>Old</h1>"
        storage = _make_storage(get_file_return=existing_content)
        db = _db_session()
        body = _update_file_body(project_id)

        saved_paths: list[str] = []
        async def _capture_save(bucket, path, data):
            saved_paths.append(path)
        storage.save_file = AsyncMock(side_effect=_capture_save)

        with (
            patch("app.api.v1.editor.router.StorageService", return_value=storage),
            patch("app.api.v1.editor.router.snapshot_repo.get_latest_version", new=AsyncMock(return_value=3)),
            patch("app.api.v1.editor.router.snapshot_repo.create", new=AsyncMock()),
        ):
            await update_file_code(body=body, db=db, user=_user(uid))

        # Первый вызов save_file — снапшот; второй — новый контент
        assert len(saved_paths) == 2
        assert "snapshots/v4/" in saved_paths[0]
        assert "snapshots" not in saved_paths[1]

    async def test_snapshot_contains_old_content(self):
        from app.api.v1.editor.router import update_file_code

        existing_content = b"<h1>Old content</h1>"
        storage = _make_storage(get_file_return=existing_content)
        db = _db_session()
        body = _update_file_body(str(uuid4()), content="<h1>New</h1>")

        saved_calls: list[tuple] = []
        async def _capture(bucket, path, data):
            saved_calls.append((path, data))
        storage.save_file = AsyncMock(side_effect=_capture)

        with (
            patch("app.api.v1.editor.router.StorageService", return_value=storage),
            patch("app.api.v1.editor.router.snapshot_repo.get_latest_version", new=AsyncMock(return_value=0)),
            patch("app.api.v1.editor.router.snapshot_repo.create", new=AsyncMock()),
        ):
            await update_file_code(body=body, db=db, user=_user())

        snapshot_path, snapshot_data = saved_calls[0]
        assert snapshot_data == existing_content
        assert "snapshots/v1/" in snapshot_path

    async def test_no_snapshot_when_file_does_not_exist(self):
        from app.api.v1.editor.router import update_file_code

        storage = _make_storage(get_file_return=None)
        db = _db_session()
        body = _update_file_body(str(uuid4()))

        with (
            patch("app.api.v1.editor.router.StorageService", return_value=storage),
            patch("app.api.v1.editor.router.snapshot_repo.create", new=AsyncMock()) as mock_create,
        ):
            await update_file_code(body=body, db=db, user=_user())

        mock_create.assert_not_called()
        db.commit.assert_not_called()

    async def test_snapshot_version_increments(self):
        from app.api.v1.editor.router import update_file_code

        project_id = str(uuid4())
        storage = _make_storage(get_file_return=b"old")
        body = _update_file_body(project_id)

        snapshot_paths: list[str] = []
        async def _capture(bucket, path, data):
            snapshot_paths.append(path)
        storage.save_file = AsyncMock(side_effect=_capture)

        with (
            patch("app.api.v1.editor.router.StorageService", return_value=storage),
            patch("app.api.v1.editor.router.snapshot_repo.get_latest_version", new=AsyncMock(return_value=7)),
            patch("app.api.v1.editor.router.snapshot_repo.create", new=AsyncMock()),
        ):
            await update_file_code(body=body, db=_db_session(), user=_user())

        assert "snapshots/v8/" in snapshot_paths[0]

    async def test_db_commit_called_after_snapshot(self):
        from app.api.v1.editor.router import update_file_code

        storage = _make_storage(get_file_return=b"old")
        db = _db_session()
        body = _update_file_body(str(uuid4()))

        with (
            patch("app.api.v1.editor.router.StorageService", return_value=storage),
            patch("app.api.v1.editor.router.snapshot_repo.get_latest_version", new=AsyncMock(return_value=0)),
            patch("app.api.v1.editor.router.snapshot_repo.create", new=AsyncMock()),
        ):
            await update_file_code(body=body, db=db, user=_user())

        db.commit.assert_called_once()
