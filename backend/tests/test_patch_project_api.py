"""Unit-тесты для PATCH /projects/{id}.

Запуск:
    cd backend
    pytest tests/test_patch_project_api.py -v
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

# fastapi.responses не заглушен в conftest — добавляем здесь
_fr = MagicMock()
_fr.StreamingResponse = MagicMock
sys.modules.setdefault("fastapi.responses", _fr)


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _user(uid: UUID | None = None) -> dict:
    uid = uid or uuid4()
    return {"internal_user_id": str(uid)}


def _project(user_id: UUID | None = None, name: str = "My Project", prompt: str = "hello") -> MagicMock:
    uid = user_id or uuid4()
    p = MagicMock()
    p.id = uuid4()
    p.user_id = uid
    p.name = name
    p.prompt = prompt
    p.s3_path = f"projects/{uid}/{p.id}"
    p.status = "ready"
    p.template_id = None
    p.created_at = MagicMock()
    return p


def _session(owned_project: MagicMock | None = None, dup_project: MagicMock | None = None):
    """
    Сессия с двумя последовательными execute():
    1-й — _get_owned_project (возвращает owned_project)
    2-й — проверка дубля имени (возвращает dup_project или None)
    """
    session = AsyncMock()

    results = []
    for val in [owned_project, dup_project]:
        r = MagicMock()
        r.scalar_one_or_none.return_value = val
        results.append(r)

    call_count = 0

    async def _execute(_query):
        nonlocal call_count
        idx = min(call_count, len(results) - 1)
        call_count += 1
        return results[idx]

    session.execute = AsyncMock(side_effect=_execute)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _body(name: str | None = None, prompt: str | None = None):
    b = MagicMock()
    b.name = name
    b.prompt = prompt
    return b


# ===========================================================================
# PATCH /projects/{id}
# ===========================================================================

@pytest.mark.asyncio
class TestUpdateProject:

    async def test_updates_name(self):
        from app.api.v1.projects.router import update_project

        uid = uuid4()
        proj = _project(user_id=uid, name="Old Name")
        session = _session(owned_project=proj, dup_project=None)

        await update_project(
            project_id=proj.id,
            body=_body(name="New Name"),
            user=_user(uid),
            session=session,
        )

        assert proj.name == "New Name"

    async def test_updates_prompt(self):
        from app.api.v1.projects.router import update_project

        uid = uuid4()
        proj = _project(user_id=uid, prompt="old prompt")
        session = _session(owned_project=proj, dup_project=None)

        await update_project(
            project_id=proj.id,
            body=_body(prompt="new prompt"),
            user=_user(uid),
            session=session,
        )

        assert proj.prompt == "new prompt"

    async def test_updates_both_fields(self):
        from app.api.v1.projects.router import update_project

        uid = uuid4()
        proj = _project(user_id=uid, name="Old", prompt="old prompt")
        session = _session(owned_project=proj, dup_project=None)

        await update_project(
            project_id=proj.id,
            body=_body(name="New", prompt="new prompt"),
            user=_user(uid),
            session=session,
        )

        assert proj.name == "New"
        assert proj.prompt == "new prompt"

    async def test_raises_404_when_project_not_found(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import update_project

        session = _session(owned_project=None)

        with pytest.raises(HTTPException) as exc_info:
            await update_project(
                project_id=uuid4(),
                body=_body(name="X"),
                user=_user(),
                session=session,
            )

        assert exc_info.value.status_code == 404

    async def test_raises_400_on_duplicate_name(self):
        from fastapi import HTTPException
        from app.api.v1.projects.router import update_project

        uid = uuid4()
        proj = _project(user_id=uid, name="Mine")
        other = _project(user_id=uid, name="Taken")
        session = _session(owned_project=proj, dup_project=other)

        with pytest.raises(HTTPException) as exc_info:
            await update_project(
                project_id=proj.id,
                body=_body(name="Taken"),
                user=_user(uid),
                session=session,
            )

        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail

    async def test_name_not_changed_when_none(self):
        from app.api.v1.projects.router import update_project

        uid = uuid4()
        proj = _project(user_id=uid, name="Keep Me")
        session = _session(owned_project=proj, dup_project=None)

        await update_project(
            project_id=proj.id,
            body=_body(name=None, prompt="new prompt"),
            user=_user(uid),
            session=session,
        )

        assert proj.name == "Keep Me"

    async def test_prompt_not_changed_when_none(self):
        from app.api.v1.projects.router import update_project

        uid = uuid4()
        proj = _project(user_id=uid, prompt="Keep Me")
        session = _session(owned_project=proj, dup_project=None)

        await update_project(
            project_id=proj.id,
            body=_body(name="New Name", prompt=None),
            user=_user(uid),
            session=session,
        )

        assert proj.prompt == "Keep Me"

    async def test_flush_and_refresh_called(self):
        from app.api.v1.projects.router import update_project

        uid = uuid4()
        proj = _project(user_id=uid)
        session = _session(owned_project=proj, dup_project=None)

        await update_project(
            project_id=proj.id,
            body=_body(name="X"),
            user=_user(uid),
            session=session,
        )

        session.flush.assert_called_once()
        session.refresh.assert_called_once_with(proj)

    async def test_same_name_allowed_for_same_project(self):
        """Переименование в то же самое имя — не конфликт (проект исключён из проверки)."""
        from app.api.v1.projects.router import update_project

        uid = uuid4()
        proj = _project(user_id=uid, name="Same Name")
        # dup=None: дубля нет, т.к. запрос excludes current project_id
        session = _session(owned_project=proj, dup_project=None)

        result = await update_project(
            project_id=proj.id,
            body=_body(name="Same Name"),
            user=_user(uid),
            session=session,
        )

        assert result is proj


# ===========================================================================
# Схема ProjectUpdate (unit-тест без роутера)
# ===========================================================================

class TestProjectUpdateSchema:

    def test_valid_name_only(self):
        from app.schemas.project import ProjectUpdate
        m = ProjectUpdate(name="Hello")
        assert m.name == "Hello"
        assert m.prompt is None

    def test_valid_prompt_only(self):
        from app.schemas.project import ProjectUpdate
        m = ProjectUpdate(prompt="Some prompt")
        assert m.prompt == "Some prompt"
        assert m.name is None

    def test_valid_both_fields(self):
        from app.schemas.project import ProjectUpdate
        m = ProjectUpdate(name="X", prompt="Y")
        assert m.name == "X"
        assert m.prompt == "Y"

    def test_raises_if_both_none(self):
        from pydantic import ValidationError
        from app.schemas.project import ProjectUpdate
        with pytest.raises(ValidationError):
            ProjectUpdate()

    def test_raises_if_prompt_empty_string(self):
        from pydantic import ValidationError
        from app.schemas.project import ProjectUpdate
        with pytest.raises(ValidationError):
            ProjectUpdate(prompt="   ")
