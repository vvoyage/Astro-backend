"""Unit-тесты для: StorageService, пайплайн генерации, задача сборки.

Запуск:
    cd backend
    pytest tests/test_new_changes.py -v
"""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _make_storage():
    """StorageService с заглушкой Minio — без реального сетевого подключения."""
    import app.services.storage as _storage_mod  # ensure module is loaded first
    from app.services.storage import StorageService

    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True   # бакеты уже существуют

    with patch.object(_storage_mod, "Minio", return_value=mock_client):
        svc = StorageService()
    # svc.client уже содержит mock_client; патч Minio больше не нужен
    return svc


def _make_db_ctx():
    """AsyncSession context manager для патча AsyncSessionFactory."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, mock_db


# ===========================================================================
# StorageService.save_file
# ===========================================================================

class TestSaveFile:
    def test_invalid_bucket_type_raises(self):
        svc = _make_storage()
        with pytest.raises(ValueError, match="Invalid bucket type"):
            import asyncio
            asyncio.run(svc.save_file("bad_bucket", "obj.txt", b"data"))

    @pytest.mark.asyncio
    async def test_bytes_forwarded_to_sync_helper(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock()

        await svc.save_file("projects", "some/path.txt", b"hello")

        svc._sync_put_object.assert_called_once_with(
            "astro-projects", "some/path.txt", b"hello"
        )

    @pytest.mark.asyncio
    async def test_bytesio_converted_to_bytes(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock()

        await svc.save_file("projects", "obj.txt", BytesIO(b"bio data"))

        svc._sync_put_object.assert_called_once_with(
            "astro-projects", "obj.txt", b"bio data"
        )

    @pytest.mark.asyncio
    async def test_templates_bucket_resolved(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock()

        await svc.save_file("templates", "base/pkg.json", b"{}")

        bucket_used = svc._sync_put_object.call_args[0][0]
        assert bucket_used == "astro-templates"

    @pytest.mark.asyncio
    async def test_sync_error_wrapped(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock(side_effect=RuntimeError("connection refused"))

        with pytest.raises(Exception, match="Error saving file to MinIO"):
            await svc.save_file("projects", "x.txt", b"data")


# ===========================================================================
# StorageService.save_source_files
# ===========================================================================

class TestSaveSourceFiles:
    @pytest.mark.asyncio
    async def test_all_files_uploaded(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock()

        files = {
            "src/pages/index.astro": "<h1/>",
            "src/components/Hero.astro": "<div/>",
        }
        await svc.save_source_files("u1", "p1", files)

        assert svc._sync_put_object.call_count == 2

    @pytest.mark.asyncio
    async def test_object_path_structure(self):
        svc = _make_storage()
        uploaded: list[str] = []
        svc._sync_put_object = MagicMock(
            side_effect=lambda _b, name, _d: uploaded.append(name)
        )

        await svc.save_source_files("user-1", "proj-1", {"pages/index.astro": "x"})

        assert uploaded[0] == "projects/user-1/proj-1/src/pages/index.astro"

    @pytest.mark.asyncio
    async def test_leading_slash_stripped(self):
        svc = _make_storage()
        uploaded: list[str] = []
        svc._sync_put_object = MagicMock(
            side_effect=lambda _b, name, _d: uploaded.append(name)
        )

        await svc.save_source_files("u", "p", {"/pages/index.astro": "x"})

        # Не должно быть двойного слеша
        assert "//" not in uploaded[0]
        assert uploaded[0].endswith("pages/index.astro")

    @pytest.mark.asyncio
    async def test_content_encoded_utf8(self):
        svc = _make_storage()
        captured: list[bytes] = []
        svc._sync_put_object = MagicMock(
            side_effect=lambda _b, _n, data: captured.append(data)
        )

        await svc.save_source_files("u", "p", {"f.astro": "Привет мир"})

        assert captured[0] == "Привет мир".encode("utf-8")

    @pytest.mark.asyncio
    async def test_empty_dict_no_calls(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock()

        await svc.save_source_files("u", "p", {})

        svc._sync_put_object.assert_not_called()


# ===========================================================================
# StorageService.create_directory
# ===========================================================================

class TestCreateDirectory:
    @pytest.mark.asyncio
    async def test_trailing_slash_appended(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock()

        await svc.create_directory("projects", "projects/u/p/src")

        name = svc._sync_put_object.call_args[0][1]
        assert name.endswith("/")

    @pytest.mark.asyncio
    async def test_no_double_slash_if_already_present(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock()

        await svc.create_directory("projects", "projects/u/p/src/")

        name = svc._sync_put_object.call_args[0][1]
        assert not name.endswith("//")

    @pytest.mark.asyncio
    async def test_empty_bytes_uploaded(self):
        svc = _make_storage()
        svc._sync_put_object = MagicMock()

        await svc.create_directory("projects", "some/dir")

        data = svc._sync_put_object.call_args[0][2]
        assert data == b""


# ===========================================================================
# StorageService.delete_directory
# ===========================================================================

class TestDeleteDirectory:
    @pytest.mark.asyncio
    async def test_all_listed_objects_removed(self):
        svc = _make_storage()
        svc._sync_list_objects = MagicMock(return_value=["a/1.txt", "a/2.txt"])
        svc._sync_remove_object = MagicMock()

        await svc.delete_directory("projects", "a/")

        assert svc._sync_remove_object.call_count == 2
        removed = {c[0][1] for c in svc._sync_remove_object.call_args_list}
        assert removed == {"a/1.txt", "a/2.txt"}

    @pytest.mark.asyncio
    async def test_empty_dir_no_remove_calls(self):
        svc = _make_storage()
        svc._sync_list_objects = MagicMock(return_value=[])
        svc._sync_remove_object = MagicMock()

        await svc.delete_directory("projects", "empty/")

        svc._sync_remove_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_bucket_raises(self):
        svc = _make_storage()
        with pytest.raises(ValueError):
            await svc.delete_directory("bad_bucket", "prefix/")


# ===========================================================================
# StorageService._sync_get_object — HTTP response lifecycle
# ===========================================================================

class TestSyncGetObjectResponseClosed:
    def _svc_with_real_client_mock(self):
        import app.services.storage as _storage_mod
        from app.services.storage import StorageService

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        with patch.object(_storage_mod, "Minio", return_value=mock_client):
            svc = StorageService()
        return svc, mock_client

    def test_response_closed_on_success(self):
        svc, mock_client = self._svc_with_real_client_mock()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"content"
        mock_client.get_object.return_value = mock_resp

        result = svc._sync_get_object("bucket", "key")

        assert result == b"content"
        mock_resp.close.assert_called_once()
        mock_resp.release_conn.assert_called_once()

    def test_response_closed_on_read_error(self):
        """Соединение закрывается даже если read() бросает исключение."""
        svc, mock_client = self._svc_with_real_client_mock()
        mock_resp = MagicMock()
        mock_resp.read.side_effect = IOError("read failed")
        mock_client.get_object.return_value = mock_resp

        with pytest.raises(IOError):
            svc._sync_get_object("bucket", "key")

        mock_resp.close.assert_called_once()
        mock_resp.release_conn.assert_called_once()


# ===========================================================================
# Пайплайн генерации — _pipeline()
# ===========================================================================

def _default_optimizer_spec():
    return {"pages": ["index"], "global_style": {"primary": "#fff"}, "components": []}


def _default_architect_files(n=1):
    return {
        "files": [
            {"path": f"src/pages/page{i}.astro", "description": f"Page {i}"}
            for i in range(n)
        ]
    }


def _default_gen_results(n=1):
    return [
        {"path": f"src/pages/page{i}.astro", "content": f"<page{i}/>"}
        for i in range(n)
    ]


_PROJ_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.mark.asyncio
class TestGenerationPipeline:
    async def _run(self, *, prompt="кофейня", model="gpt-5.4",
                   optimizer_spec=None, architect_files=None, gen_results=None):
        from app.workers.tasks.generation import _pipeline

        opt_spec = optimizer_spec or _default_optimizer_spec()
        arch_files = architect_files or _default_architect_files(1)
        gen_res = gen_results or _default_gen_results(len(arch_files["files"]))

        ctx, db = _make_db_ctx()
        mock_storage = AsyncMock()
        mock_redis_inst = MagicMock()

        with patch("app.workers.tasks.generation.AsyncSessionFactory", return_value=ctx), \
             patch("app.workers.tasks.generation.project_repo.update_status",
                   new_callable=AsyncMock) as mock_update_status, \
             patch("app.workers.tasks.generation.OptimizerAgent") as MockOpt, \
             patch("app.workers.tasks.generation.ArchitectAgent") as MockArch, \
             patch("app.workers.tasks.generation.CodeGeneratorAgent") as MockGen, \
             patch("app.workers.tasks.generation.redis_lib.from_url",
                   return_value=mock_redis_inst), \
             patch("app.workers.tasks.build.run_build") as mock_build_task:

            MockOpt.return_value.run = AsyncMock(return_value=opt_spec)
            MockArch.return_value.run = AsyncMock(return_value=arch_files)
            MockGen.return_value.run = AsyncMock(side_effect=list(gen_res))

            await _pipeline(_PROJ_ID, _USER_ID, prompt, model, mock_storage)

        return dict(
            mock_update_status=mock_update_status,
            mock_storage=mock_storage,
            mock_build_task=mock_build_task,
            mock_redis=mock_redis_inst,
            MockOpt=MockOpt,
            MockArch=MockArch,
            MockGen=MockGen,
        )

    async def test_project_marked_generating(self):
        r = await self._run()
        r["mock_update_status"].assert_awaited_once()
        _, _, status = r["mock_update_status"].call_args[0]
        assert status == "generating"

    async def test_optimizer_called_with_prompt(self):
        r = await self._run(prompt="my prompt")
        call_input = r["MockOpt"].return_value.run.call_args[0][0]
        assert call_input["prompt"] == "my prompt"

    async def test_architect_receives_optimizer_output(self):
        spec = {"pages": ["about"], "components": ["Footer"]}
        r = await self._run(optimizer_spec=spec,
                            gen_results=_default_gen_results(1))
        call_input = r["MockArch"].return_value.run.call_args[0][0]
        assert call_input == spec

    async def test_code_gen_called_once_per_file(self):
        arch = _default_architect_files(3)
        r = await self._run(architect_files=arch, gen_results=_default_gen_results(3))
        assert r["MockGen"].return_value.run.await_count == 3

    async def test_save_source_files_called_with_correct_args(self):
        arch = _default_architect_files(1)
        gen = _default_gen_results(1)
        r = await self._run(architect_files=arch, gen_results=gen)

        r["mock_storage"].save_source_files.assert_awaited_once()
        user_id, project_id, files = r["mock_storage"].save_source_files.call_args[0]
        assert user_id == _USER_ID
        assert project_id == _PROJ_ID
        assert "src/pages/page0.astro" in files
        assert files["src/pages/page0.astro"] == "<page0/>"

    async def test_build_task_queued_after_save(self):
        r = await self._run()
        r["mock_build_task"].delay.assert_called_once_with(_PROJ_ID, _USER_ID)

    async def test_redis_status_written_multiple_times(self):
        r = await self._run()
        # Минимум 3 стадии: optimizer, architect, code_generator
        assert r["mock_redis"].set.call_count >= 3

    async def test_redis_final_stage_is_building(self):
        r = await self._run()
        last_payload = json.loads(r["mock_redis"].set.call_args_list[-1][0][1])
        assert last_payload["stage"] == "building"

    async def test_model_passed_to_all_agents(self):
        r = await self._run(model="gpt-5.4")
        r["MockOpt"].assert_called_once_with(model="gpt-5.4")
        r["MockArch"].assert_called_once_with(model="gpt-5.4")
        r["MockGen"].assert_called_once_with(model="gpt-5.4")

    async def test_empty_file_list_no_gen_calls(self):
        arch = {"files": []}
        r = await self._run(architect_files=arch, gen_results=[])
        r["MockGen"].return_value.run.assert_not_awaited()

    async def test_empty_file_list_save_called_with_empty_dict(self):
        arch = {"files": []}
        r = await self._run(architect_files=arch, gen_results=[])
        _, _, files = r["mock_storage"].save_source_files.call_args[0]
        assert files == {}


# ===========================================================================
# Задача сборки — _build()
# ===========================================================================

@pytest.mark.asyncio
class TestBuildTask:
    async def _run(self, job_statuses=None, expect_error=None):
        from app.workers.tasks.build import _build

        if job_statuses is None:
            job_statuses = ["Completed"]

        ctx, _ = _make_db_ctx()
        mock_redis_inst = MagicMock()

        with patch("app.workers.tasks.build.KubernetesService") as MockK8s, \
             patch("app.workers.tasks.build.AsyncSessionFactory", return_value=ctx), \
             patch("app.workers.tasks.build.project_repo.update_status",
                   new_callable=AsyncMock) as mock_update, \
             patch("app.workers.tasks.build.redis_lib.from_url",
                   return_value=mock_redis_inst), \
             patch("app.workers.tasks.build._BUILD_POLL_INTERVAL", new=0), \
             patch("asyncio.sleep", new_callable=AsyncMock):

            k8s = MockK8s.return_value
            k8s.create_build_job = AsyncMock(return_value=f"build-{_USER_ID}-{_PROJ_ID}")
            k8s.get_job_status = AsyncMock(side_effect=list(job_statuses))
            k8s.get_pod_logs = AsyncMock(return_value="build logs here")

            if expect_error:
                with pytest.raises(expect_error):
                    await _build(_PROJ_ID, _USER_ID)
                return dict(mock_update=mock_update, mock_redis=mock_redis_inst, k8s=k8s)

            await _build(_PROJ_ID, _USER_ID)

        return dict(mock_update=mock_update, mock_redis=mock_redis_inst, k8s=k8s)

    async def test_k8s_job_created_with_correct_args(self):
        r = await self._run()
        r["k8s"].create_build_job.assert_awaited_once_with(_USER_ID, _PROJ_ID)

    async def test_project_status_set_to_ready(self):
        r = await self._run()
        r["mock_update"].assert_awaited_once()
        _, _, status = r["mock_update"].call_args[0]
        assert status == "ready"

    async def test_redis_done_100_on_success(self):
        r = await self._run()
        last = json.loads(r["mock_redis"].set.call_args_list[-1][0][1])
        assert last["stage"] == "done"
        assert last["progress"] == 100

    async def test_polls_multiple_times_before_complete(self):
        r = await self._run(job_statuses=["Running", "Running", "Running", "Completed"])
        assert r["k8s"].get_job_status.await_count == 4

    async def test_raises_runtime_error_on_failed_job(self):
        await self._run(job_statuses=["Failed"], expect_error=RuntimeError)

    async def test_redis_no_done_status_on_failed_job(self):
        """When job fails, 'done' status must never be written to Redis."""
        r = await self._run(job_statuses=["Failed"], expect_error=RuntimeError)
        payloads = [
            json.loads(c[0][1]) for c in r["mock_redis"].set.call_args_list
        ]
        assert not any(p["stage"] == "done" for p in payloads)

    async def test_pod_logs_fetched_on_failure(self):
        r = await self._run(job_statuses=["Failed"], expect_error=RuntimeError)
        r["k8s"].get_pod_logs.assert_awaited_once()

    async def test_timeout_raises(self):
        """Если job не завершается, должен бросить TimeoutError."""
        from app.workers.tasks.build import _BUILD_TIMEOUT

        ctx, _ = _make_db_ctx()

        with patch("app.workers.tasks.build.KubernetesService") as MockK8s, \
             patch("app.workers.tasks.build.AsyncSessionFactory", return_value=ctx), \
             patch("app.workers.tasks.build.project_repo.update_status",
                   new_callable=AsyncMock), \
             patch("app.workers.tasks.build.redis_lib.from_url", return_value=MagicMock()), \
             patch("app.workers.tasks.build._BUILD_POLL_INTERVAL", new=_BUILD_TIMEOUT + 1), \
             patch("asyncio.sleep", new_callable=AsyncMock):

            k8s = MockK8s.return_value
            k8s.create_build_job = AsyncMock(return_value="build-job")
            k8s.get_job_status = AsyncMock(return_value="Running")

            with pytest.raises(TimeoutError):
                from app.workers.tasks.build import _build
                await _build(_PROJ_ID, _USER_ID)

    async def test_update_status_not_called_on_failure(self):
        """При Failed job статус проекта не должен меняться на ready."""
        r = await self._run(job_statuses=["Failed"], expect_error=RuntimeError)
        # update_status может не вызываться вовсе, или вызываться с "failed" — но не с "ready"
        if r["mock_update"].called:
            _, _, status = r["mock_update"].call_args[0]
            assert status != "ready"
