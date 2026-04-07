"""Unit-тесты для api/v1/projects/router.py и StorageService.copy_directory.

Запуск:
    cd backend
    pytest tests/test_projects_api.py -v
"""
from __future__ import annotations

import io
import zipfile
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import UUID, uuid4

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_storage():
    """StorageService без реального Minio-подключения."""
    import app.services.storage as _storage_mod
    from app.services.storage import StorageService

    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    with patch.object(_storage_mod, "Minio", return_value=mock_client):
        svc = StorageService()
    return svc


def _user(uid: UUID | None = None) -> dict:
    uid = uid or uuid4()
    return {"internal_user_id": str(uid), "_uid": uid}


def _project(user_id: UUID | None = None, s3_path: str | None = None) -> MagicMock:
    uid = user_id or uuid4()
    p = MagicMock()
    p.id = uuid4()
    p.user_id = uid
    p.name = "Тестовый проект"
    p.prompt = "какой-то промпт"
    p.s3_path = s3_path or f"projects/{uid}/000"
    p.status = "queued"
    p.created_at = MagicMock()
    p.template_id = None
    return p


def _session(scalar=None, scalars_list=None):
    """AsyncMock сессии с pre-configured execute()."""
    session = AsyncMock()

    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalars_list or []
    result.scalars.return_value = scalars_mock

    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


def _session_multi(*scalars):
    """Сессия с разными scalar_one_or_none() при последовательных execute()."""
    session = AsyncMock()

    results = []
    for s in scalars:
        r = MagicMock()
        r.scalar_one_or_none.return_value = s
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = s if isinstance(s, list) else []
        r.scalars.return_value = scalars_mock
        results.append(r)

    session.execute = AsyncMock(side_effect=results)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


# ===========================================================================
# StorageService.copy_directory
# ===========================================================================

class TestCopyDirectory:
    @pytest.mark.asyncio
    async def test_copies_all_listed_objects(self):
        svc = _make_storage()
        svc._sync_list_objects = MagicMock(
            return_value=["projects/u/000/src/a.astro", "projects/u/000/src/b.astro"]
        )
        svc._sync_copy_object = MagicMock()

        await svc.copy_directory("projects", "projects/u/000", "projects/u/proj-id")

        assert svc._sync_copy_object.call_count == 2

    @pytest.mark.asyncio
    async def test_destination_path_constructed_correctly(self):
        svc = _make_storage()
        svc._sync_list_objects = MagicMock(
            return_value=["projects/u/000/src/index.astro"]
        )
        copied: list[tuple] = []
        svc._sync_copy_object = MagicMock(side_effect=lambda b, s, d: copied.append((s, d)))

        await svc.copy_directory("projects", "projects/u/000", "projects/u/abc")

        src, dst = copied[0]
        assert src == "projects/u/000/src/index.astro"
        assert dst == "projects/u/abc/src/index.astro"

    @pytest.mark.asyncio
    async def test_trailing_slash_normalised(self):
        """copy_directory должен корректно работать даже если слеш уже есть."""
        svc = _make_storage()
        svc._sync_list_objects = MagicMock(
            return_value=["projects/u/000/src/f.astro"]
        )
        copied: list[tuple] = []
        svc._sync_copy_object = MagicMock(side_effect=lambda b, s, d: copied.append((s, d)))

        await svc.copy_directory("projects", "projects/u/000/", "projects/u/xyz/")

        _, dst = copied[0]
        assert dst == "projects/u/xyz/src/f.astro"
        assert "//" not in dst

    @pytest.mark.asyncio
    async def test_empty_directory_no_copy_calls(self):
        svc = _make_storage()
        svc._sync_list_objects = MagicMock(return_value=[])
        svc._sync_copy_object = MagicMock()

        await svc.copy_directory("projects", "projects/u/000", "projects/u/abc")

        svc._sync_copy_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_bucket_type_raises(self):
        svc = _make_storage()
        with pytest.raises(ValueError, match="Invalid bucket type"):
            await svc.copy_directory("bad_bucket", "src/", "dst/")

    @pytest.mark.asyncio
    async def test_sync_error_wrapped(self):
        svc = _make_storage()
        svc._sync_list_objects = MagicMock(return_value=["x/a.txt"])
        svc._sync_copy_object = MagicMock(side_effect=RuntimeError("minio down"))

        with pytest.raises(Exception, match="Error copying directory in MinIO"):
            await svc.copy_directory("projects", "x/", "y/")


# ===========================================================================
# list_projects
# ===========================================================================

@pytest.mark.asyncio
class TestListProjects:
    async def test_returns_projects_for_user(self):
        from app.api.v1.projects.router import list_projects

        uid = uuid4()
        projects = [_project(uid), _project(uid)]
        session = _session(scalars_list=projects)
        # execute возвращает результат с .scalars().all()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = projects
        session.execute = AsyncMock(return_value=result_mock)

        result = await list_projects(user=_user(uid), session=session)

        assert result == projects

    async def test_returns_empty_list_when_no_projects(self):
        from app.api.v1.projects.router import list_projects

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result_mock)

        result = await list_projects(user=_user(), session=session)

        assert result == []


# ===========================================================================
# get_project
# ===========================================================================

@pytest.mark.asyncio
class TestGetProject:
    async def test_returns_project_when_found(self):
        from app.api.v1.projects.router import get_project

        uid = uuid4()
        proj = _project(uid)
        result = await get_project(
            project_id=proj.id,
            user=_user(uid),
            session=_session(scalar=proj),
        )
        assert result is proj

    async def test_raises_404_when_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import get_project

        with pytest.raises(HTTPException) as exc:
            await get_project(
                project_id=uuid4(),
                user=_user(),
                session=_session(scalar=None),
            )

        assert exc.value.status_code == 404


# ===========================================================================
# create_project
# ===========================================================================

@pytest.mark.asyncio
class TestCreateProject:
    async def test_raises_400_on_duplicate_name(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import create_project
        from app.schemas.project import ProjectCreate

        uid = uuid4()
        existing = _project(uid)
        session = _session(scalar=existing)

        body = ProjectCreate(name="Мой проект", prompt="промпт")
        with pytest.raises(HTTPException) as exc:
            await create_project(body=body, user=_user(uid), session=session)

        assert exc.value.status_code == 400
        assert "already exists" in exc.value.detail

    async def test_raises_400_when_no_prompt_and_no_template(self):
        from fastapi import HTTPException
        from app.schemas.project import ProjectCreate

        with pytest.raises(ValueError):
            ProjectCreate(name="Проект")

    async def test_raises_400_when_prompt_too_long(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import create_project
        from app.schemas.project import ProjectCreate

        session = _session(scalar=None)
        body = ProjectCreate(name="Проект", prompt="x" * 2001)

        with pytest.raises(HTTPException) as exc:
            await create_project(body=body, user=_user(), session=session)

        assert exc.value.status_code == 400
        assert "2000" in exc.value.detail

    async def test_raises_404_when_template_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import create_project
        from app.schemas.project import ProjectCreate

        # execute: первый вызов — дубликат (None), второй — шаблон (None)
        session = _session_multi(None, None)
        body = ProjectCreate(name="Проект", template_id=uuid4())

        with pytest.raises(HTTPException) as exc:
            await create_project(body=body, user=_user(), session=session)

        assert exc.value.status_code == 404

    async def test_success_returns_project_preview(self):
        from app.api.v1.projects.router import create_project
        from app.schemas.project import ProjectCreate, ProjectPreview

        uid = uuid4()
        session = _session(scalar=None)
        body = ProjectCreate(name="Coffee", prompt="landing")

        mock_storage = AsyncMock()
        mock_db_project = MagicMock()
        mock_db_project.id = uuid4()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage), \
             patch("app.api.v1.projects.router.ProjectModel", return_value=mock_db_project):
            result = await create_project(body=body, user=_user(uid), session=session)

        assert isinstance(result, ProjectPreview)
        assert "000" in result.path

    async def test_success_creates_minio_structure(self):
        from app.api.v1.projects.router import create_project
        from app.schemas.project import ProjectCreate

        uid = uuid4()
        session = _session(scalar=None)
        body = ProjectCreate(name="Project", prompt="prompt")
        mock_storage = AsyncMock()
        mock_db_project = MagicMock()
        mock_db_project.id = uuid4()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage), \
             patch("app.api.v1.projects.router.ProjectModel", return_value=mock_db_project):
            await create_project(body=body, user=_user(uid), session=session)

        mock_storage.cleanup_default_project.assert_awaited_once_with(str(uid))
        mock_storage.create_project_structure.assert_awaited_once()

    async def test_storage_error_raises_500(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import create_project
        from app.schemas.project import ProjectCreate

        session = _session(scalar=None)
        body = ProjectCreate(name="Project", prompt="prompt")
        mock_storage = AsyncMock()
        mock_storage.cleanup_default_project.side_effect = RuntimeError("minio down")
        mock_db_project = MagicMock()
        mock_db_project.id = uuid4()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage), \
             patch("app.api.v1.projects.router.ProjectModel", return_value=mock_db_project):
            with pytest.raises(HTTPException) as exc:
                await create_project(body=body, user=_user(), session=session)

        assert exc.value.status_code == 500


# ===========================================================================
# save_project
# ===========================================================================

@pytest.mark.asyncio
class TestSaveProject:
    async def test_moves_files_from_000_to_project_id(self):
        from app.api.v1.projects.router import save_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/000")
        session = _session(scalar=proj)
        mock_storage = AsyncMock()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            await save_project(project_id=proj.id, user=_user(uid), session=session)

        mock_storage.copy_directory.assert_awaited_once()
        src, dst = (
            mock_storage.copy_directory.call_args[0][1],
            mock_storage.copy_directory.call_args[0][2],
        )
        assert src == f"projects/{uid}/000"
        assert str(proj.id) in dst

    async def test_deletes_000_slot_after_copy(self):
        from app.api.v1.projects.router import save_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/000")
        session = _session(scalar=proj)
        mock_storage = AsyncMock()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            await save_project(project_id=proj.id, user=_user(uid), session=session)

        mock_storage.delete_directory.assert_awaited_once()
        prefix_arg = mock_storage.delete_directory.call_args[0][1]
        assert "000" in prefix_arg

    async def test_idempotent_when_already_saved(self):
        """Если s3_path уже не 000, MinIO не трогаем."""
        from app.api.v1.projects.router import save_project

        uid = uuid4()
        proj_id = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/{proj_id}")
        session = _session(scalar=proj)
        mock_storage = AsyncMock()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            result = await save_project(project_id=proj.id, user=_user(uid), session=session)

        mock_storage.copy_directory.assert_not_awaited()
        mock_storage.delete_directory.assert_not_awaited()
        assert result is proj

    async def test_raises_404_when_project_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import save_project

        with pytest.raises(HTTPException) as exc:
            await save_project(
                project_id=uuid4(),
                user=_user(),
                session=_session(scalar=None),
            )

        assert exc.value.status_code == 404

    async def test_storage_error_raises_500(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import save_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/000")
        session = _session(scalar=proj)
        mock_storage = AsyncMock()
        mock_storage.copy_directory.side_effect = RuntimeError("minio error")

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            with pytest.raises(HTTPException) as exc:
                await save_project(project_id=proj.id, user=_user(uid), session=session)

        assert exc.value.status_code == 500

    async def test_s3_path_updated_in_db(self):
        from app.api.v1.projects.router import save_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/000")
        session = _session(scalar=proj)
        mock_storage = AsyncMock()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            await save_project(project_id=proj.id, user=_user(uid), session=session)

        # s3_path должен быть обновлён, flush и refresh вызваны
        assert proj.s3_path != f"projects/{uid}/000"
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(proj)


# ===========================================================================
# export_project
# ===========================================================================

@pytest.mark.asyncio
class TestExportProject:
    async def test_returns_zip_response(self):
        from fastapi.responses import StreamingResponse
        from app.api.v1.projects.router import export_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/abc")
        proj.name = "MyProject"
        session = _session(scalar=proj)
        mock_storage = AsyncMock()
        mock_storage.list_files.return_value = [f"projects/{uid}/abc/src/index.astro"]
        mock_storage.get_file.return_value = b"<h1>Hello</h1>"

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            response = await export_project(
                project_id=proj.id, user=_user(uid), session=session
            )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "application/zip"

    async def test_zip_contains_expected_files(self):
        from app.api.v1.projects.router import export_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/abc")
        proj.name = "MyProject"
        session = _session(scalar=proj)
        mock_storage = AsyncMock()
        mock_storage.list_files.return_value = [
            f"projects/{uid}/abc/src/index.astro",
            f"projects/{uid}/abc/src/components/Hero.astro",
        ]
        mock_storage.get_file.side_effect = [b"index content", b"hero content"]

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            response = await export_project(
                project_id=proj.id, user=_user(uid), session=session
            )

        buf = io.BytesIO()
        async for chunk in response.body_iterator:
            buf.write(chunk)
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()

        assert "src/index.astro" in names
        assert "src/components/Hero.astro" in names

    async def test_directory_markers_skipped(self):
        """Объекты, заканчивающиеся на '/', не попадают в архив."""
        from app.api.v1.projects.router import export_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/abc")
        proj.name = "MyProject"
        session = _session(scalar=proj)
        mock_storage = AsyncMock()
        mock_storage.list_files.return_value = [
            f"projects/{uid}/abc/src/",            # маркер директории
            f"projects/{uid}/abc/src/index.astro",
        ]
        mock_storage.get_file.return_value = b"content"

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            response = await export_project(
                project_id=proj.id, user=_user(uid), session=session
            )

        buf = io.BytesIO()
        async for chunk in response.body_iterator:
            buf.write(chunk)
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()

        assert not any(n.endswith("/") for n in names)

    async def test_raises_404_when_no_files(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import export_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/abc")
        session = _session(scalar=proj)
        mock_storage = AsyncMock()
        mock_storage.list_files.return_value = []

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            with pytest.raises(HTTPException) as exc:
                await export_project(
                    project_id=proj.id, user=_user(uid), session=session
                )

        assert exc.value.status_code == 404

    async def test_raises_404_when_project_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import export_project

        with pytest.raises(HTTPException) as exc:
            await export_project(
                project_id=uuid4(),
                user=_user(),
                session=_session(scalar=None),
            )

        assert exc.value.status_code == 404

    async def test_content_disposition_contains_project_name(self):
        """Имя проекта (в т.ч. кириллица) должно быть в Content-Disposition через RFC 5987."""
        import urllib.parse
        from app.api.v1.projects.router import export_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/abc")
        proj.name = "MyCoffeeShop"
        session = _session(scalar=proj)
        mock_storage = AsyncMock()
        mock_storage.list_files.return_value = [f"projects/{uid}/abc/src/f.astro"]
        mock_storage.get_file.return_value = b"x"

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            response = await export_project(
                project_id=proj.id, user=_user(uid), session=session
            )

        disposition = response.headers["Content-Disposition"]
        assert "MyCoffeeShop" in disposition
        assert "filename*=UTF-8''" in disposition


# ===========================================================================
# delete_project
# ===========================================================================

@pytest.mark.asyncio
class TestDeleteProject:
    async def test_deletes_from_db(self):
        from fastapi import Response
        from app.api.v1.projects.router import delete_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/abc")
        session = _session(scalar=proj)
        mock_storage = AsyncMock()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            response = await delete_project(
                project_id=proj.id, user=_user(uid), session=session
            )

        session.delete.assert_awaited_once_with(proj)
        session.flush.assert_awaited_once()

    async def test_deletes_minio_directory(self):
        from app.api.v1.projects.router import delete_project

        uid = uuid4()
        proj = _project(uid, s3_path=f"projects/{uid}/abc")
        session = _session(scalar=proj)
        mock_storage = AsyncMock()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            await delete_project(
                project_id=proj.id, user=_user(uid), session=session
            )

        mock_storage.delete_directory.assert_awaited_once()
        prefix_arg = mock_storage.delete_directory.call_args[0][1]
        assert proj.s3_path in prefix_arg

    async def test_returns_204(self):
        from fastapi import Response
        from app.api.v1.projects.router import delete_project

        uid = uuid4()
        proj = _project(uid)
        session = _session(scalar=proj)
        mock_storage = AsyncMock()

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            response = await delete_project(
                project_id=proj.id, user=_user(uid), session=session
            )

        assert isinstance(response, Response)
        assert response.status_code == 204

    async def test_raises_404_when_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import delete_project

        with pytest.raises(HTTPException) as exc:
            await delete_project(
                project_id=uuid4(),
                user=_user(),
                session=_session(scalar=None),
            )

        assert exc.value.status_code == 404

    async def test_db_delete_proceeds_even_if_minio_fails(self):
        """MinIO ошибка не должна отменять удаление из БД."""
        from app.api.v1.projects.router import delete_project

        uid = uuid4()
        proj = _project(uid)
        session = _session(scalar=proj)
        mock_storage = AsyncMock()
        mock_storage.delete_directory.side_effect = RuntimeError("minio down")

        with patch("app.api.v1.projects.router.StorageService", return_value=mock_storage):
            await delete_project(
                project_id=proj.id, user=_user(uid), session=session
            )

        session.delete.assert_awaited_once_with(proj)
