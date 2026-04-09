"""Unit-тесты для периодической задачи sync_users._sync.

Запуск:
    cd backend
    pytest tests/test_sync_users.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _http_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


class _FakeSessionCtx:
    """Лёгкий async-контекстный менеджер для замены AsyncSessionFactory."""

    def __init__(self, rows: list):
        self._rows = rows
        self.execute = AsyncMock()
        self.commit = AsyncMock()
        self._configured = False

    async def __aenter__(self):
        if not self._configured:
            result = MagicMock()
            result.all.return_value = self._rows
            self.execute = AsyncMock(return_value=result)
            self._configured = True
        return self

    async def __aexit__(self, *args):
        return False


def _fake_http_client(token_resp: MagicMock, user_check_resp: MagicMock) -> MagicMock:
    client = AsyncMock()
    client.post = AsyncMock(return_value=token_resp)
    client.get = AsyncMock(return_value=user_check_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSync:

    async def test_no_users_returns_zero_counts(self):
        """Нет пользователей с keycloak_id — сразу возвращаем 0/0."""
        from app.workers.tasks.sync_users import _sync

        session = _FakeSessionCtx(rows=[])

        with patch("app.workers.tasks.sync_users.AsyncSessionFactory", return_value=session):
            result = await _sync()

        assert result == {"checked": 0, "purged": 0}

    async def test_user_exists_in_keycloak_not_purged(self):
        """Пользователь есть в Keycloak (200) → не трогаем PG."""
        from app.workers.tasks.sync_users import _sync

        user_row = (uuid4(), "kc-alive", "alive@example.com")
        session = _FakeSessionCtx(rows=[user_row])

        token_resp = _http_response(200, {"access_token": "tok"})
        user_resp = _http_response(200)  # пользователь найден
        http_client = _fake_http_client(token_resp, user_resp)

        with patch("app.workers.tasks.sync_users.AsyncSessionFactory", return_value=session), \
             patch("app.workers.tasks.sync_users.httpx.AsyncClient", return_value=http_client):
            result = await _sync()

        assert result["checked"] == 1
        assert result["purged"] == 0

    async def test_deleted_user_purged_from_db(self):
        """Пользователь удалён из Keycloak (404) → каскадное удаление из PG."""
        from app.workers.tasks.sync_users import _sync

        user_id = uuid4()
        user_row = (user_id, "kc-dead", "dead@example.com")

        # Первая сессия — SELECT пользователей
        first_session = _FakeSessionCtx(rows=[user_row])

        # Вторая сессия — внутри цикла удаления (SELECT project_ids + bulk deletes)
        no_project_result = MagicMock()
        no_project_result.all.return_value = []
        second_session = _FakeSessionCtx(rows=[])
        second_session.execute = AsyncMock(return_value=no_project_result)
        second_session._configured = True

        call_count = {"n": 0}
        def _factory():
            call_count["n"] += 1
            return first_session if call_count["n"] == 1 else second_session

        token_resp = _http_response(200, {"access_token": "tok"})
        not_found_resp = _http_response(404)   # пользователь удалён
        http_client = _fake_http_client(token_resp, not_found_resp)

        with patch("app.workers.tasks.sync_users.AsyncSessionFactory", side_effect=_factory), \
             patch("app.workers.tasks.sync_users.httpx.AsyncClient", return_value=http_client):
            result = await _sync()

        assert result["checked"] == 1
        assert result["purged"] == 1
        second_session.commit.assert_called_once()

    async def test_deleted_user_with_projects_runs_cascade(self):
        """Удалённый пользователь с проектами → bulk delete всех связанных записей."""
        from app.workers.tasks.sync_users import _sync

        user_id = uuid4()
        project_id = uuid4()
        user_row = (user_id, "kc-dead", "dead@example.com")

        first_session = _FakeSessionCtx(rows=[user_row])

        # Вторая сессия — project_ids возвращает один проект
        second_session = _FakeSessionCtx(rows=[])
        project_result = MagicMock()
        project_result.all.return_value = [(project_id,)]
        delete_result = MagicMock()
        second_session.execute = AsyncMock(
            side_effect=[project_result] + [delete_result] * 5  # select + 4 bulk deletes + delete user
        )
        second_session._configured = True

        call_count = {"n": 0}
        def _factory():
            call_count["n"] += 1
            return first_session if call_count["n"] == 1 else second_session

        token_resp = _http_response(200, {"access_token": "tok"})
        not_found_resp = _http_response(404)
        http_client = _fake_http_client(token_resp, not_found_resp)

        with patch("app.workers.tasks.sync_users.AsyncSessionFactory", side_effect=_factory), \
             patch("app.workers.tasks.sync_users.httpx.AsyncClient", return_value=http_client):
            result = await _sync()

        assert result["purged"] == 1
        # 1 select project_ids + 4 bulk deletes + 1 delete user = 6 вызовов execute
        assert second_session.execute.call_count == 6

    async def test_keycloak_unreachable_returns_error_no_db_changes(self):
        """Keycloak недоступен → возвращаем error, PG не трогаем."""
        import httpx
        from app.workers.tasks.sync_users import _sync

        user_row = (uuid4(), "kc-id", "user@example.com")
        session = _FakeSessionCtx(rows=[user_row])

        broken_client = AsyncMock()
        broken_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        broken_client.__aenter__ = AsyncMock(return_value=broken_client)
        broken_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.workers.tasks.sync_users.AsyncSessionFactory", return_value=session), \
             patch("app.workers.tasks.sync_users.httpx.AsyncClient", return_value=broken_client):
            result = await _sync()

        assert "error" in result
        assert result["purged"] == 0
        assert result["checked"] == 1

    async def test_multiple_users_mixed_result(self):
        """Несколько пользователей: часть есть в Keycloak, часть нет."""
        from app.workers.tasks.sync_users import _sync

        alive_id = uuid4()
        dead_id = uuid4()
        rows = [
            (alive_id, "kc-alive", "alive@example.com"),
            (dead_id, "kc-dead", "dead@example.com"),
        ]

        first_session = _FakeSessionCtx(rows=rows)

        purge_session = _FakeSessionCtx(rows=[])
        no_projects = MagicMock()
        no_projects.all.return_value = []
        purge_session.execute = AsyncMock(return_value=no_projects)
        purge_session._configured = True

        call_count = {"n": 0}
        def _factory():
            call_count["n"] += 1
            return first_session if call_count["n"] == 1 else purge_session

        token_resp = _http_response(200, {"access_token": "tok"})

        # alive → 200, dead → 404
        responses = [_http_response(200), _http_response(404)]
        resp_iter = iter(responses)
        http_client = AsyncMock()
        http_client.post = AsyncMock(return_value=token_resp)
        http_client.get = AsyncMock(side_effect=lambda *a, **kw: next(resp_iter))
        http_client.__aenter__ = AsyncMock(return_value=http_client)
        http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.workers.tasks.sync_users.AsyncSessionFactory", side_effect=_factory), \
             patch("app.workers.tasks.sync_users.httpx.AsyncClient", return_value=http_client):
            result = await _sync()

        assert result["checked"] == 2
        assert result["purged"] == 1
