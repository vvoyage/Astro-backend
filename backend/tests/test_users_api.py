"""Unit-тесты для GET /users/me и PATCH /users/me.

Запуск:
    cd backend
    pytest tests/test_users_api.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _db_user(
    uid=None,
    email: str = "user@example.com",
    full_name: str | None = "Test User",
) -> MagicMock:
    u = MagicMock()
    u.id = uid or uuid4()
    u.email = email
    u.full_name = full_name
    u.is_active = True
    u.created_at = MagicMock()
    u.updated_at = MagicMock()
    return u


def _user_payload(db_user=None) -> dict:
    """Auth payload с _db_user, как возвращает get_current_user."""
    u = db_user or _db_user()
    return {
        "internal_user_id": str(u.id),
        "_db_user": u,
    }


def _user_payload_no_cache(db_user=None) -> dict:
    """Auth payload без _db_user (редкий случай — нет в кэше)."""
    u = db_user or _db_user()
    return {"internal_user_id": str(u.id)}


def _session(scalar=None) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _update_body(full_name: str | None = "New Name") -> MagicMock:
    b = MagicMock()
    b.full_name = full_name
    return b


# ===========================================================================
# GET /users/me
# ===========================================================================

@pytest.mark.asyncio
class TestGetMe:

    async def test_returns_db_user_from_payload(self):
        """_db_user уже в payload — никакого запроса в БД."""
        from app.api.v1.users.router import get_me

        u = _db_user(full_name="Alice")
        payload = _user_payload(u)
        db = _session()

        result = await get_me(user=payload, db=db)

        assert result is u
        db.execute.assert_not_called()

    async def test_fetches_from_db_when_no_cache(self):
        """Если _db_user нет в payload — делает запрос в БД."""
        from app.api.v1.users.router import get_me

        u = _db_user()
        payload = _user_payload_no_cache(u)
        db = _session(scalar=u)

        result = await get_me(user=payload, db=db)

        assert result is u
        db.execute.assert_called_once()

    async def test_raises_404_when_user_not_found_in_db(self):
        """Пользователь отсутствует в БД (крайний случай)."""
        from fastapi import HTTPException
        from app.api.v1.users.router import get_me

        payload = _user_payload_no_cache()
        db = _session(scalar=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_me(user=payload, db=db)

        assert exc_info.value.status_code == 404

    async def test_returns_correct_user_data(self):
        from app.api.v1.users.router import get_me

        u = _db_user(email="alice@example.com", full_name="Alice Wonderland")
        result = await get_me(user=_user_payload(u), db=_session())

        assert result.email == "alice@example.com"
        assert result.full_name == "Alice Wonderland"


# ===========================================================================
# PATCH /users/me
# ===========================================================================

@pytest.mark.asyncio
class TestUpdateMe:

    async def test_updates_full_name(self):
        from app.api.v1.users.router import update_me

        u = _db_user(full_name="Old Name")
        db = _session()

        await update_me(body=_update_body("New Name"), user=_user_payload(u), db=db)

        assert u.full_name == "New Name"

    async def test_flush_and_refresh_called(self):
        from app.api.v1.users.router import update_me

        u = _db_user()
        db = _session()

        await update_me(body=_update_body("X"), user=_user_payload(u), db=db)

        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(u)

    async def test_returns_updated_user(self):
        from app.api.v1.users.router import update_me

        u = _db_user(full_name="Before")
        db = _session()

        result = await update_me(body=_update_body("After"), user=_user_payload(u), db=db)

        assert result is u

    async def test_raises_400_when_full_name_is_none(self):
        from fastapi import HTTPException
        from app.api.v1.users.router import update_me

        with pytest.raises(HTTPException) as exc_info:
            await update_me(
                body=_update_body(None),
                user=_user_payload(),
                db=_session(),
            )

        assert exc_info.value.status_code == 400

    async def test_fetches_from_db_when_no_cache(self):
        """Если _db_user нет в payload — делает запрос в БД."""
        from app.api.v1.users.router import update_me

        u = _db_user()
        payload = _user_payload_no_cache(u)
        db = _session(scalar=u)

        result = await update_me(body=_update_body("Name"), user=payload, db=db)

        db.execute.assert_called_once()
        assert result is u

    async def test_raises_404_when_user_not_found_in_db(self):
        from fastapi import HTTPException
        from app.api.v1.users.router import update_me

        payload = _user_payload_no_cache()
        db = _session(scalar=None)

        with pytest.raises(HTTPException) as exc_info:
            await update_me(body=_update_body("X"), user=payload, db=db)

        assert exc_info.value.status_code == 404

    async def test_can_set_empty_string_name(self):
        """Пустая строка — допустимое значение (отличается от None)."""
        from app.api.v1.users.router import update_me

        u = _db_user(full_name="Had Name")
        db = _session()

        await update_me(body=_update_body(""), user=_user_payload(u), db=db)

        assert u.full_name == ""
