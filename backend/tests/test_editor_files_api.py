"""Unit-тесты для GET /editor/files?project_id={id}.

Запуск:
    cd backend
    pytest tests/test_editor_files_api.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_storage(list_files_return: list[str] | None = None):
    import app.services.storage as _storage_mod
    from app.services.storage import StorageService

    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    with patch.object(_storage_mod, "Minio", return_value=mock_client):
        svc = StorageService()

    svc.list_files = AsyncMock(return_value=list_files_return or [])
    return svc


def _user(uid: str | None = None) -> dict:
    uid = uid or str(uuid4())
    return {"internal_user_id": uid}


# ===========================================================================
# GET /editor/files
# ===========================================================================

@pytest.mark.asyncio
class TestListProjectFiles:

    async def test_returns_relative_file_paths(self):
        from app.api.v1.editor.router import list_project_files

        uid = str(uuid4())
        pid = str(uuid4())
        prefix = f"projects/{uid}/{pid}/src/"
        minio_paths = [
            f"{prefix}index.astro",
            f"{prefix}components/Header.astro",
            f"{prefix}pages/about.astro",
        ]
        storage = _make_storage(minio_paths)

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            result = await list_project_files(project_id=pid, user=_user(uid))

        assert result["project_id"] == pid
        assert set(result["files"]) == {
            "index.astro",
            "components/Header.astro",
            "pages/about.astro",
        }

    async def test_filters_directory_markers(self):
        """Объекты MinIO, оканчивающиеся на '/', не должны попадать в список."""
        from app.api.v1.editor.router import list_project_files

        uid = str(uuid4())
        pid = str(uuid4())
        prefix = f"projects/{uid}/{pid}/src/"
        minio_paths = [
            f"{prefix}",           # маркер директории
            f"{prefix}components/",  # маркер поддиректории
            f"{prefix}index.astro",
        ]
        storage = _make_storage(minio_paths)

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            result = await list_project_files(project_id=pid, user=_user(uid))

        assert result["files"] == ["index.astro"]

    async def test_returns_empty_list_when_no_files(self):
        from app.api.v1.editor.router import list_project_files

        storage = _make_storage([])

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            result = await list_project_files(project_id=str(uuid4()), user=_user())

        assert result["files"] == []

    async def test_calls_storage_with_correct_prefix(self):
        """Убеждаемся, что StorageService.list_files вызван с правильным path."""
        from app.api.v1.editor.router import list_project_files

        uid = str(uuid4())
        pid = str(uuid4())
        storage = _make_storage([])

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            await list_project_files(project_id=pid, user=_user(uid))

        storage.list_files.assert_called_once_with(
            "projects",
            f"projects/{uid}/{pid}/src/",
        )

    async def test_raises_500_when_storage_fails(self):
        from fastapi import HTTPException
        from app.api.v1.editor.router import list_project_files

        storage = _make_storage()
        storage.list_files = AsyncMock(side_effect=Exception("MinIO connection refused"))

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            with pytest.raises(HTTPException) as exc_info:
                await list_project_files(project_id=str(uuid4()), user=_user())

        assert exc_info.value.status_code == 500
        assert "MinIO connection refused" in exc_info.value.detail

    async def test_file_path_does_not_contain_prefix(self):
        """Проверяем что в files нет полного пути MinIO."""
        from app.api.v1.editor.router import list_project_files

        uid = str(uuid4())
        pid = str(uuid4())
        prefix = f"projects/{uid}/{pid}/src/"
        storage = _make_storage([f"{prefix}deep/nested/file.astro"])

        with patch("app.api.v1.editor.router.StorageService", return_value=storage):
            result = await list_project_files(project_id=pid, user=_user(uid))

        assert result["files"] == ["deep/nested/file.astro"]
        assert not any(uid in f for f in result["files"])
