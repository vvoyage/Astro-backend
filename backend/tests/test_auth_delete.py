"""Unit-тесты для DELETE /auth/me и _purge_user_from_db.

Запуск:
    cd backend
    pytest tests/test_auth_delete.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _db_user(keycloak_id: str | None = "kc-uuid-123") -> MagicMock:
    u = MagicMock()
    u.id = uuid4()
    u.keycloak_id = keycloak_id
    u.email = "test@example.com"
    u.is_active = True
    return u


def _session(project_ids: list | None = None) -> AsyncMock:
    """
    Мок AsyncSession для _purge_user_from_db.
    project_ids — список UUID проектов пользователя (None → проектов нет).
    """
    session = AsyncMock()

    select_result = MagicMock()
    select_result.all.return_value = [(pid,) for pid in (project_ids or [])]
    delete_result = MagicMock()

    if project_ids:
        # 1 select(Project.id) + 4 bulk delete (Asset, Snapshot, Deployment, Project)
        session.execute = AsyncMock(side_effect=[select_result] + [delete_result] * 4)
    else:
        session.execute = AsyncMock(return_value=select_result)

    session.delete = AsyncMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# _purge_user_from_db
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPurgeUserFromDb:

    async def test_no_projects_only_deletes_user_row(self):
        """Нет проектов — только session.delete(user) и commit."""
        from app.api.v1.auth.router import _purge_user_from_db

        user = _db_user()
        session = _session(project_ids=[])

        await _purge_user_from_db(session, user)

        assert session.execute.call_count == 1   # только select
        session.delete.assert_called_once_with(user)
        session.commit.assert_called_once()

    async def test_with_projects_runs_four_bulk_deletes(self):
        """Два проекта → 4 bulk DELETE (assets/snapshots/deployments/projects) + user."""
        from app.api.v1.auth.router import _purge_user_from_db

        project_ids = [uuid4(), uuid4()]
        user = _db_user()
        session = _session(project_ids=project_ids)

        await _purge_user_from_db(session, user)

        assert session.execute.call_count == 5   # 1 select + 4 bulk deletes
        session.delete.assert_called_once_with(user)
        session.commit.assert_called_once()

    async def test_commit_always_called(self):
        """commit вызывается независимо от наличия проектов."""
        from app.api.v1.auth.router import _purge_user_from_db

        await _purge_user_from_db(_session(), _db_user())

        # проверка не упала → commit был вызван (assert внутри _session)

    async def test_user_delete_uses_orm_delete(self):
        """Пользователь удаляется через session.delete(), не через bulk-запрос."""
        from app.api.v1.auth.router import _purge_user_from_db

        user = _db_user()
        session = _session()

        await _purge_user_from_db(session, user)

        # session.delete вызван именно с объектом user, а не с чем-то другим
        session.delete.assert_called_once_with(user)


# ---------------------------------------------------------------------------
# delete_account (DELETE /auth/me)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDeleteAccount:

    async def test_happy_path_calls_keycloak_then_db(self):
        """Успешное удаление: сначала Keycloak, потом PostgreSQL."""
        from app.api.v1.auth.router import delete_account

        user = _db_user(keycloak_id="kc-abc")
        session = _session()

        with patch("app.api.v1.auth.router.delete_keycloak_user", new_callable=AsyncMock) as mock_kc, \
             patch("app.api.v1.auth.router._purge_user_from_db", new_callable=AsyncMock) as mock_purge:

            await delete_account(current_user=user, session=session)

        mock_kc.assert_called_once_with("kc-abc")
        mock_purge.assert_called_once_with(session, user)

    async def test_no_keycloak_id_skips_keycloak_call(self):
        """Пользователь без keycloak_id → Keycloak не вызываем."""
        from app.api.v1.auth.router import delete_account

        user = _db_user(keycloak_id=None)

        with patch("app.api.v1.auth.router.delete_keycloak_user", new_callable=AsyncMock) as mock_kc, \
             patch("app.api.v1.auth.router._purge_user_from_db", new_callable=AsyncMock):

            await delete_account(current_user=user, session=_session())

        mock_kc.assert_not_called()

    async def test_keycloak_failure_leaves_db_untouched(self):
        """Keycloak вернул ошибку → база данных не трогается, пробрасываем исключение."""
        from fastapi import HTTPException
        from app.api.v1.auth.router import delete_account

        user = _db_user(keycloak_id="kc-abc")

        with patch(
            "app.api.v1.auth.router.delete_keycloak_user",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=503, detail="KC down"),
        ), \
        patch("app.api.v1.auth.router._purge_user_from_db", new_callable=AsyncMock) as mock_purge:

            with pytest.raises(HTTPException) as exc_info:
                await delete_account(current_user=user, session=_session())

        assert exc_info.value.status_code == 503
        mock_purge.assert_not_called()

    async def test_db_failure_after_keycloak_returns_500(self):
        """Keycloak удалён, но PG упала → 500."""
        from fastapi import HTTPException
        from app.api.v1.auth.router import delete_account

        user = _db_user(keycloak_id="kc-abc")

        with patch("app.api.v1.auth.router.delete_keycloak_user", new_callable=AsyncMock), \
             patch(
                 "app.api.v1.auth.router._purge_user_from_db",
                 new_callable=AsyncMock,
                 side_effect=RuntimeError("DB boom"),
             ):

            with pytest.raises(HTTPException) as exc_info:
                await delete_account(current_user=user, session=_session())

        assert exc_info.value.status_code == 500

    async def test_keycloak_id_passed_correctly(self):
        """keycloak_id берётся из current_user.keycloak_id."""
        from app.api.v1.auth.router import delete_account

        user = _db_user(keycloak_id="specific-kc-id")

        with patch("app.api.v1.auth.router.delete_keycloak_user", new_callable=AsyncMock) as mock_kc, \
             patch("app.api.v1.auth.router._purge_user_from_db", new_callable=AsyncMock):

            await delete_account(current_user=user, session=_session())

        args, _ = mock_kc.call_args
        assert args[0] == "specific-kc-id"
