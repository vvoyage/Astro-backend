"""Unit-тесты для POST /editor/edit и workers/tasks/edit._edit().

Запуск:
    cd backend
    pytest tests/test_edit_element.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_storage(
    get_file_return: bytes | None = b"<h1>Old</h1>",
) -> MagicMock:
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


def _edit_body(project_id: str | None = None) -> MagicMock:
    body = MagicMock()
    body.project_id = project_id or str(uuid4())
    body.element = MagicMock()
    body.element.file_path = "src/pages/index.astro"
    body.element.editable_id = "hero-title"
    body.instruction = "Измени заголовок"
    body.ai_model = "gpt-4o-mini"
    return body


# ===========================================================================
# POST /editor/edit — роутер
# ===========================================================================

@pytest.mark.asyncio
class TestEditElementRouter:

    async def test_returns_202_with_task_fields(self):
        from app.api.v1.editor.router import edit_element

        project_id = str(uuid4())
        body = _edit_body(project_id)
        redis = AsyncMock()
        mock_task = MagicMock()
        mock_task.id = "celery-task-uuid"

        with patch("app.api.v1.editor.router.edit_element_task") as mock_celery:
            mock_celery.delay.return_value = mock_task
            result = await edit_element(
                body=body,
                db=AsyncMock(),
                redis=redis,
                user=_user(),
            )

        assert result.task_id == "celery-task-uuid"
        assert result.project_id == project_id
        assert result.file_path == "src/pages/index.astro"
        assert result.status == "queued"

    async def test_sets_redis_status_queued(self):
        from app.api.v1.editor.router import edit_element

        project_id = str(uuid4())
        body = _edit_body(project_id)
        redis = AsyncMock()

        with patch("app.api.v1.editor.router.edit_element_task") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="task-id")
            await edit_element(body=body, db=AsyncMock(), redis=redis, user=_user())

        redis.set.assert_called_once()
        call_args = redis.set.call_args
        redis_key = call_args[0][0]
        assert redis_key == f"generation:{project_id}:status"
        import json
        payload = json.loads(call_args[0][1])
        assert payload["stage"] == "queued"
        assert payload["progress"] == 0

    async def test_dispatches_celery_task_with_correct_args(self):
        from app.api.v1.editor.router import edit_element

        uid = str(uuid4())
        project_id = str(uuid4())
        body = _edit_body(project_id)
        body.element.file_path = "src/components/Hero.astro"
        body.element.editable_id = "hero-cta"
        body.instruction = "Сделай кнопку красной"
        body.ai_model = "gpt-4o"

        with patch("app.api.v1.editor.router.edit_element_task") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="t")
            await edit_element(
                body=body,
                db=AsyncMock(),
                redis=AsyncMock(),
                user=_user(uid),
            )

        mock_celery.delay.assert_called_once_with(
            project_id=project_id,
            user_id=uid,
            file_path="src/components/Hero.astro",
            element_id="hero-cta",
            prompt="Сделай кнопку красной",
            ai_model="gpt-4o",
            project_context="",
        )

    async def test_uses_internal_user_id_not_keycloak_sub(self):
        """Убедимся что task получает internal UUID, а не keycloak sub."""
        from app.api.v1.editor.router import edit_element

        internal_id = str(uuid4())
        user = {"internal_user_id": internal_id, "sub": "keycloak-sub-123"}

        with patch("app.api.v1.editor.router.edit_element_task") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="t")
            await edit_element(
                body=_edit_body(),
                db=AsyncMock(),
                redis=AsyncMock(),
                user=user,
            )

        _, kwargs = mock_celery.delay.call_args
        assert kwargs["user_id"] == internal_id


# ===========================================================================
# workers/tasks/edit._edit() — async core logic
# ===========================================================================

@pytest.mark.asyncio
class TestEditTaskCore:

    async def _run_edit(
        self,
        project_id: str,
        user_id: str,
        storage: MagicMock,
        llm_new_code: str = "<h1>Updated</h1>",
        snapshot_latest_version: int = 0,
    ) -> None:
        """Запускает _edit() с полным набором моков."""
        from app.workers.tasks.edit import _edit

        mock_agent = MagicMock()
        mock_agent.edit = AsyncMock(return_value=llm_new_code)

        # run_build импортируется локально внутри _edit(), поэтому патчим в build-модуле
        with (
            patch("app.workers.tasks.edit.EditorAgent", return_value=mock_agent),
            patch("app.workers.tasks.edit.snapshot_repo.get_latest_version",
                  new=AsyncMock(return_value=snapshot_latest_version)),
            patch("app.workers.tasks.edit.snapshot_repo.create", new=AsyncMock()),
            patch("app.workers.tasks.edit.AsyncSessionFactory") as mock_session_factory,
            patch("app.workers.tasks.edit._set_redis_status"),
            patch("app.workers.tasks.build.run_build") as mock_build,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            mock_session_factory.return_value = mock_db
            mock_build.delay = MagicMock()

            await _edit(
                project_id=project_id,
                user_id=user_id,
                file_path="src/pages/index.astro",
                element_id="hero",
                prompt="Измени заголовок",
                ai_model="gpt-4o",
                project_context="",
                storage=storage,
            )

    async def test_downloads_file_from_minio(self):
        uid, pid = str(uuid4()), str(uuid4())
        storage = _make_storage(get_file_return=b"<h1>Old</h1>")

        await self._run_edit(pid, uid, storage)

        storage.get_file.assert_called_once_with(
            "projects",
            f"projects/{uid}/{pid}/src/pages/index.astro",
        )

    async def test_raises_when_file_not_found(self):
        from app.workers.tasks.edit import _edit

        storage = _make_storage(get_file_return=None)
        uid, pid = str(uuid4()), str(uuid4())

        with (
            patch("app.workers.tasks.edit._set_redis_status"),
            pytest.raises(FileNotFoundError),
        ):
            await _edit(
                project_id=pid,
                user_id=uid,
                file_path="src/missing.astro",
                element_id="",
                prompt="p",
                ai_model="gpt-4o",
                project_context="",
                storage=storage,
            )

    async def test_creates_snapshot_before_editing(self):
        from app.workers.tasks.edit import _edit

        uid, pid = str(uuid4()), str(uuid4())
        storage = _make_storage(get_file_return=b"old code")
        saved_paths: list[str] = []

        async def capture_save(bucket, path, data):
            saved_paths.append(path)

        storage.save_file = AsyncMock(side_effect=capture_save)
        mock_agent = MagicMock()
        mock_agent.edit = AsyncMock(return_value="new code")

        with (
            patch("app.workers.tasks.edit.EditorAgent", return_value=mock_agent),
            patch("app.workers.tasks.edit.snapshot_repo.get_latest_version",
                  new=AsyncMock(return_value=2)),
            patch("app.workers.tasks.edit.snapshot_repo.create", new=AsyncMock()),
            patch("app.workers.tasks.edit.AsyncSessionFactory") as msf,
            patch("app.workers.tasks.edit._set_redis_status"),
            patch("app.workers.tasks.build.run_build") as mb,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            msf.return_value = mock_db
            mb.delay = MagicMock()

            await _edit(
                project_id=pid, user_id=uid,
                file_path="src/pages/index.astro", element_id="",
                prompt="p", ai_model="gpt-4o", project_context="",
                storage=storage,
            )

        # первый save_file — снапшот
        assert len(saved_paths) == 2
        assert f"snapshots/v3/" in saved_paths[0]
        # второй — обновлённый файл
        assert "snapshots" not in saved_paths[1]

    async def test_snapshot_contains_original_content(self):
        from app.workers.tasks.edit import _edit

        original = b"<h1>Original</h1>"
        uid, pid = str(uuid4()), str(uuid4())
        storage = _make_storage(get_file_return=original)
        saved_calls: list[tuple] = []

        async def capture(bucket, path, data):
            saved_calls.append((path, data))

        storage.save_file = AsyncMock(side_effect=capture)
        mock_agent = MagicMock()
        mock_agent.edit = AsyncMock(return_value="new")

        with (
            patch("app.workers.tasks.edit.EditorAgent", return_value=mock_agent),
            patch("app.workers.tasks.edit.snapshot_repo.get_latest_version",
                  new=AsyncMock(return_value=0)),
            patch("app.workers.tasks.edit.snapshot_repo.create", new=AsyncMock()),
            patch("app.workers.tasks.edit.AsyncSessionFactory") as msf,
            patch("app.workers.tasks.edit._set_redis_status"),
            patch("app.workers.tasks.build.run_build") as mb,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            msf.return_value = mock_db
            mb.delay = MagicMock()

            await _edit(
                project_id=pid, user_id=uid,
                file_path="src/index.astro", element_id="",
                prompt="p", ai_model="gpt-4o", project_context="",
                storage=storage,
            )

        snapshot_path, snapshot_data = saved_calls[0]
        assert snapshot_data == original
        assert "snapshots/v1/" in snapshot_path

    async def test_calls_editor_agent_with_file_content(self):
        from app.workers.tasks.edit import _edit

        uid, pid = str(uuid4()), str(uuid4())
        original_code = "const x = 1;"
        storage = _make_storage(get_file_return=original_code.encode())
        mock_agent = MagicMock()
        mock_agent.edit = AsyncMock(return_value="const x = 2;")

        with (
            patch("app.workers.tasks.edit.EditorAgent", return_value=mock_agent) as MockAgent,
            patch("app.workers.tasks.edit.snapshot_repo.get_latest_version",
                  new=AsyncMock(return_value=0)),
            patch("app.workers.tasks.edit.snapshot_repo.create", new=AsyncMock()),
            patch("app.workers.tasks.edit.AsyncSessionFactory") as msf,
            patch("app.workers.tasks.edit._set_redis_status"),
            patch("app.workers.tasks.build.run_build") as mb,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            msf.return_value = mock_db
            mb.delay = MagicMock()

            await _edit(
                project_id=pid, user_id=uid,
                file_path="src/index.astro", element_id="hero",
                prompt="Сделай красным", ai_model="gpt-4o-mini", project_context="",
                storage=storage,
            )

        MockAgent.assert_called_once_with(model="gpt-4o-mini")
        mock_agent.edit.assert_called_once_with(
            current_code=original_code,
            element_id="hero",
            prompt="Сделай красным",
            project_context="",
        )

    async def test_saves_new_code_to_minio(self):
        from app.workers.tasks.edit import _edit

        uid, pid = str(uuid4()), str(uuid4())
        new_code = "<h1>Updated by LLM</h1>"
        storage = _make_storage(get_file_return=b"old")
        saved_calls: list[tuple] = []

        async def capture(bucket, path, data):
            saved_calls.append((path, data))

        storage.save_file = AsyncMock(side_effect=capture)
        mock_agent = MagicMock()
        mock_agent.edit = AsyncMock(return_value=new_code)

        with (
            patch("app.workers.tasks.edit.EditorAgent", return_value=mock_agent),
            patch("app.workers.tasks.edit.snapshot_repo.get_latest_version",
                  new=AsyncMock(return_value=0)),
            patch("app.workers.tasks.edit.snapshot_repo.create", new=AsyncMock()),
            patch("app.workers.tasks.edit.AsyncSessionFactory") as msf,
            patch("app.workers.tasks.edit._set_redis_status"),
            patch("app.workers.tasks.build.run_build") as mb,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            msf.return_value = mock_db
            mb.delay = MagicMock()

            await _edit(
                project_id=pid, user_id=uid,
                file_path="src/pages/index.astro", element_id="",
                prompt="p", ai_model="gpt-4o", project_context="",
                storage=storage,
            )

        # второй вызов save_file — обновлённый файл
        _, final_path, final_data = saved_calls[1][0], saved_calls[1][0], saved_calls[1][1]
        assert final_data == new_code.encode("utf-8")

    async def test_queues_rebuild_after_save(self):
        from app.workers.tasks.edit import _edit

        uid, pid = str(uuid4()), str(uuid4())
        storage = _make_storage(get_file_return=b"old")
        mock_agent = MagicMock()
        mock_agent.edit = AsyncMock(return_value="new code")

        with (
            patch("app.workers.tasks.edit.EditorAgent", return_value=mock_agent),
            patch("app.workers.tasks.edit.snapshot_repo.get_latest_version",
                  new=AsyncMock(return_value=0)),
            patch("app.workers.tasks.edit.snapshot_repo.create", new=AsyncMock()),
            patch("app.workers.tasks.edit.AsyncSessionFactory") as msf,
            patch("app.workers.tasks.edit._set_redis_status"),
            patch("app.workers.tasks.build.run_build") as mock_build,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            msf.return_value = mock_db
            mock_build.delay = MagicMock()

            await _edit(
                project_id=pid, user_id=uid,
                file_path="src/index.astro", element_id="",
                prompt="p", ai_model="gpt-4o", project_context="",
                storage=storage,
            )

        mock_build.delay.assert_called_once_with(pid, uid)

    async def test_snapshot_version_increments_correctly(self):
        from app.workers.tasks.edit import _edit

        uid, pid = str(uuid4()), str(uuid4())
        storage = _make_storage(get_file_return=b"code")
        saved_paths: list[str] = []

        async def capture(bucket, path, data):
            saved_paths.append(path)

        storage.save_file = AsyncMock(side_effect=capture)
        mock_agent = MagicMock()
        mock_agent.edit = AsyncMock(return_value="new")

        with (
            patch("app.workers.tasks.edit.EditorAgent", return_value=mock_agent),
            patch("app.workers.tasks.edit.snapshot_repo.get_latest_version",
                  new=AsyncMock(return_value=5)),
            patch("app.workers.tasks.edit.snapshot_repo.create", new=AsyncMock()),
            patch("app.workers.tasks.edit.AsyncSessionFactory") as msf,
            patch("app.workers.tasks.edit._set_redis_status"),
            patch("app.workers.tasks.build.run_build") as mb,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            msf.return_value = mock_db
            mb.delay = MagicMock()

            await _edit(
                project_id=pid, user_id=uid,
                file_path="src/index.astro", element_id="",
                prompt="p", ai_model="gpt-4o", project_context="",
                storage=storage,
            )

        assert "snapshots/v6/" in saved_paths[0]

    async def test_redis_progress_stages(self):
        """_set_redis_status вызывается на ключевых этапах pipeline."""
        from app.workers.tasks.edit import _edit

        uid, pid = str(uuid4()), str(uuid4())
        storage = _make_storage(get_file_return=b"code")
        mock_agent = MagicMock()
        mock_agent.edit = AsyncMock(return_value="new")

        with (
            patch("app.workers.tasks.edit.EditorAgent", return_value=mock_agent),
            patch("app.workers.tasks.edit.snapshot_repo.get_latest_version",
                  new=AsyncMock(return_value=0)),
            patch("app.workers.tasks.edit.snapshot_repo.create", new=AsyncMock()),
            patch("app.workers.tasks.edit.AsyncSessionFactory") as msf,
            patch("app.workers.tasks.edit._set_redis_status") as mock_redis,
            patch("app.workers.tasks.build.run_build") as mb,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            msf.return_value = mock_db
            mb.delay = MagicMock()

            await _edit(
                project_id=pid, user_id=uid,
                file_path="src/index.astro", element_id="",
                prompt="p", ai_model="gpt-4o", project_context="",
                storage=storage,
            )

        stages = [c[0][1] for c in mock_redis.call_args_list]
        assert "editing" in stages
        assert "building" in stages
        # строго: editing появляется раньше building
        assert stages.index("editing") < stages.index("building")
