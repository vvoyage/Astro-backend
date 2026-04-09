"""Unit-тесты для изменений в KubernetesService.create_build_job().

Проверяет что build-команда содержит шаги скачивания и запуска post-build.js.
Все K8s/сетевые вызовы замокированы.

Запуск:
    cd backend
    pytest tests/test_kubernetes_post_build.py -v
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Хелпер: вытащить shell-команду из созданного K8s Job
# ---------------------------------------------------------------------------

def _extract_build_command(create_call_kwargs: dict) -> str:
    """Из аргументов create_namespaced_job вытаскивает строку args[0]."""
    job: MagicMock = create_call_kwargs["body"]
    containers = job.spec.template.spec.containers
    assert len(containers) == 1
    return containers[0].args[0]


async def _create_job_and_get_command(user_id: str = "u1", project_id: str = "p1") -> str:
    """Запускает create_build_job и возвращает shell-скрипт из первого контейнера."""
    from app.services.kubernetes import KubernetesService

    with (
        patch("app.services.kubernetes.config"),
        patch("app.services.kubernetes.client") as mock_k8s_client,
    ):
        # Настраиваем mock BatchV1Api
        mock_batch = MagicMock()
        mock_batch.read_namespaced_job.side_effect = MagicMock(
            side_effect=lambda **kw: (_ for _ in ()).throw(
                type("ApiException", (Exception,), {"status": 404})()
            )
        )
        mock_batch.create_namespaced_job.return_value = MagicMock()

        # Используем реальные датаклассы, чтобы Job строился нормально
        mock_k8s_client.CoreV1Api.return_value = MagicMock()
        mock_k8s_client.BatchV1Api.return_value = mock_batch

        # V1Job и дочерние объекты строим реальными (передаём kwargs напрямую)
        class _Obj:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        for cls_name in [
            "V1Job", "V1ObjectMeta", "V1JobSpec", "V1PodTemplateSpec",
            "V1PodSpec", "V1Container", "V1EnvVar", "V1ResourceRequirements",
            "V1VolumeMount", "V1Volume", "V1PersistentVolumeClaimVolumeSource",
            "V1DeleteOptions",
        ]:
            setattr(mock_k8s_client, cls_name, _Obj)

        # ApiException для try/except в коде
        class _ApiEx(Exception):
            def __init__(self, status=404):
                self.status = status

        mock_k8s_client.exceptions = MagicMock()
        mock_k8s_client.exceptions.ApiException = _ApiEx
        mock_batch.read_namespaced_job.side_effect = _ApiEx(404)

        svc = KubernetesService()
        svc.batch_v1 = mock_batch
        svc.v1 = MagicMock()

        await svc.create_build_job(user_id, project_id)

        create_call = mock_batch.create_namespaced_job.call_args
        job_obj = create_call[1]["body"]
        return job_obj.spec.template.spec.containers[0].args[0]


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestKubernetesPostBuildStep:

    async def test_command_downloads_post_build_cjs_from_minio(self):
        cmd = await _create_job_and_get_command()
        assert "mc cp minio/astro-assets/post-build.cjs" in cmd

    async def test_command_runs_node_post_build(self):
        cmd = await _create_job_and_get_command()
        assert "node post-build.cjs" in cmd

    async def test_post_build_runs_after_npm_build(self):
        cmd = await _create_job_and_get_command()
        npm_build_pos = cmd.index("npm run build")
        post_build_pos = cmd.index("node post-build.cjs")
        assert post_build_pos > npm_build_pos

    async def test_post_build_runs_before_mc_cp_dist(self):
        cmd = await _create_job_and_get_command()
        post_build_pos = cmd.index("node post-build.cjs")
        upload_pos = cmd.index("mc cp --recursive dist/")
        assert post_build_pos < upload_pos

    async def test_mc_cp_post_build_downloads_to_current_dir(self):
        """Скрипт должен быть скачан в ./ (рядом с dist/)."""
        cmd = await _create_job_and_get_command()
        assert "mc cp minio/astro-assets/post-build.cjs ./post-build.cjs" in cmd

    async def test_create_astro_step_still_present(self):
        """create-astro не трогаем — должен остаться."""
        cmd = await _create_job_and_get_command()
        assert "create-astro" in cmd

    async def test_npm_install_still_present(self):
        cmd = await _create_job_and_get_command()
        assert "npm install" in cmd

    async def test_final_dist_upload_still_present(self):
        cmd = await _create_job_and_get_command()
        assert "mc cp --recursive dist/" in cmd
