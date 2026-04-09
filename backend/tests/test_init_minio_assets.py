"""Unit-тесты для расширенного backend/scripts/init_minio.py.

Проверяет:
- _get_minio_client читает настройки из os.environ
- main() создаёт бакет astro-assets и загружает post-build.js
- поведение при уже существующих бакетах

Запуск:
    cd backend
    pytest tests/test_init_minio_assets.py -v
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Скрипт лежит в scripts/, не в app/ — добавляем путь вручную
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# _get_minio_client
# ---------------------------------------------------------------------------

class TestGetMinioClient:

    def test_reads_endpoint_from_env(self, monkeypatch):
        monkeypatch.setenv("MINIO_ENDPOINT", "minio.example.com:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
        monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
        monkeypatch.setenv("MINIO_SECURE", "false")

        captured = {}

        class FakeMinio:
            def __init__(self, endpoint, **kwargs):
                captured["endpoint"] = endpoint
                captured.update(kwargs)

        with patch("minio.Minio", FakeMinio):
            import importlib, init_minio
            importlib.reload(init_minio)
            init_minio._get_minio_client()

        assert captured["endpoint"] == "minio.example.com:9000"

    def test_strips_http_prefix_from_endpoint(self, monkeypatch):
        monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "k")
        monkeypatch.setenv("MINIO_SECRET_KEY", "s")
        monkeypatch.setenv("MINIO_SECURE", "false")

        captured = {}

        class FakeMinio:
            def __init__(self, endpoint, **kwargs):
                captured["endpoint"] = endpoint

        with patch("minio.Minio", FakeMinio):
            import importlib, init_minio
            importlib.reload(init_minio)
            init_minio._get_minio_client()

        assert not captured["endpoint"].startswith("http://")

    def test_strips_https_prefix_from_endpoint(self, monkeypatch):
        monkeypatch.setenv("MINIO_ENDPOINT", "https://minio:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "k")
        monkeypatch.setenv("MINIO_SECRET_KEY", "s")
        monkeypatch.setenv("MINIO_SECURE", "true")

        captured = {}

        class FakeMinio:
            def __init__(self, endpoint, **kwargs):
                captured["endpoint"] = endpoint

        with patch("minio.Minio", FakeMinio):
            import importlib, init_minio
            importlib.reload(init_minio)
            init_minio._get_minio_client()

        assert not captured["endpoint"].startswith("https://")

    def test_secure_true_when_env_is_true(self, monkeypatch):
        monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "k")
        monkeypatch.setenv("MINIO_SECRET_KEY", "s")
        monkeypatch.setenv("MINIO_SECURE", "true")

        captured = {}

        class FakeMinio:
            def __init__(self, endpoint, **kwargs):
                captured.update(kwargs)

        with patch("minio.Minio", FakeMinio):
            import importlib, init_minio
            importlib.reload(init_minio)
            init_minio._get_minio_client()

        assert captured["secure"] is True

    def test_secure_false_when_env_is_false(self, monkeypatch):
        monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "k")
        monkeypatch.setenv("MINIO_SECRET_KEY", "s")
        monkeypatch.setenv("MINIO_SECURE", "false")

        captured = {}

        class FakeMinio:
            def __init__(self, endpoint, **kwargs):
                captured.update(kwargs)

        with patch("minio.Minio", FakeMinio):
            import importlib, init_minio
            importlib.reload(init_minio)
            init_minio._get_minio_client()

        assert captured["secure"] is False

    def test_defaults_used_when_env_absent(self, monkeypatch):
        for key in ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_SECURE"]:
            monkeypatch.delenv(key, raising=False)

        captured = {}

        class FakeMinio:
            def __init__(self, endpoint, **kwargs):
                captured["endpoint"] = endpoint
                captured.update(kwargs)

        with patch("minio.Minio", FakeMinio):
            import importlib, init_minio
            importlib.reload(init_minio)
            init_minio._get_minio_client()

        assert captured["endpoint"] == "localhost:9000"
        assert captured["access_key"] == "minioadmin"
        assert captured["secret_key"] == "minioadmin"
        assert captured["secure"] is False


# ---------------------------------------------------------------------------
# main() — astro-assets бакет и post-build.js
# ---------------------------------------------------------------------------

def _make_client(bucket_exists_returns: dict[str, bool] | None = None) -> MagicMock:
    """Возвращает mock Minio-клиента."""
    client = MagicMock()
    if bucket_exists_returns:
        client.bucket_exists.side_effect = lambda b: bucket_exists_returns.get(b, False)
    else:
        client.bucket_exists.return_value = False
    return client


class TestMainAssetsUpload:

    def _run_main(self, client: MagicMock):
        import importlib, init_minio
        importlib.reload(init_minio)
        with patch.object(init_minio, "_get_minio_client", return_value=client):
            init_minio.main()
        return client

    def test_creates_astro_assets_bucket_if_not_exists(self):
        client = _make_client({"astro-templates": False, "astro-assets": False})
        self._run_main(client)
        created_buckets = [c[0][0] for c in client.make_bucket.call_args_list]
        assert "astro-assets" in created_buckets

    def test_does_not_create_astro_assets_bucket_if_exists(self):
        client = _make_client({"astro-templates": True, "astro-assets": True})
        self._run_main(client)
        created_buckets = [c[0][0] for c in client.make_bucket.call_args_list]
        assert "astro-assets" not in created_buckets

    def test_uploads_post_build_cjs_to_astro_assets(self):
        client = _make_client()
        self._run_main(client)

        upload_calls = client.put_object.call_args_list
        uploaded = {
            (c[0][0], c[0][1])   # (bucket, object_name)
            for c in upload_calls
        }
        assert ("astro-assets", "post-build.cjs") in uploaded

    def test_post_build_cjs_content_type_is_javascript(self):
        client = _make_client()
        self._run_main(client)

        for c in client.put_object.call_args_list:
            bucket = c[0][0]
            obj = c[0][1]
            if bucket == "astro-assets" and obj == "post-build.cjs":
                assert c[1]["content_type"] == "application/javascript"
                return
        pytest.fail("post-build.cjs upload not found")

    def test_post_build_cjs_data_is_non_empty(self):
        client = _make_client()
        self._run_main(client)

        for c in client.put_object.call_args_list:
            bucket = c[0][0]
            obj = c[0][1]
            if bucket == "astro-assets" and obj == "post-build.cjs":
                data: io.BytesIO = c[0][2]
                content = data.read()
                assert len(content) > 0
                assert b"postMessage" in content
                return
        pytest.fail("post-build.cjs upload not found")

    def test_astro_templates_bucket_still_created(self):
        """Оригинальное поведение не сломано — astro-templates создаётся."""
        client = _make_client()
        self._run_main(client)
        created = [c[0][0] for c in client.make_bucket.call_args_list]
        assert "astro-templates" in created

    def test_templates_still_uploaded(self):
        """Оригинальные шаблоны (package.json и др.) загружаются."""
        client = _make_client()
        self._run_main(client)
        uploaded_objects = [c[0][1] for c in client.put_object.call_args_list]
        assert any("package.json" in o for o in uploaded_objects)
        assert any("astro.config.mjs" in o for o in uploaded_objects)
