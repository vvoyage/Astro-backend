"""Интеграционные тесты Keycloak auth flow.

Проверяет полный цикл:
  - регистрация через POST /auth/register
  - получение токена из Keycloak
  - синхронизация в PostgreSQL через POST /auth/sync
  - защищённые эндпоинты с токеном и без
  - ролевой доступ (user vs admin)
  - идемпотентность и обработка ошибок

Требования (всё должно быть запущено):
  - Keycloak на http://localhost:8080  (admin / admin)
  - FastAPI backend на http://localhost:8001
  - PostgreSQL + Redis (используются backend'ом)

Запуск:
    cd backend
    pytest tests/test_keycloak_flow.py -v
    pytest tests/test_keycloak_flow.py -v -s   # с выводом print
"""
from __future__ import annotations

import uuid
from typing import Generator

import httpx
import pytest


# Конфигурация

BACKEND   = "http://localhost:8001/api/v1"
KC_BASE   = "http://localhost:8080"
KC_REALM  = "astro-service"
KC_ADMIN_REALM = "master"
KC_ADMIN_CLIENT = "admin-cli"
KC_ADMIN_USER   = "admin"
KC_ADMIN_PASS   = "admin"
KC_FRONTEND_CLIENT = "astro-frontend"

# Уникальный suffix чтобы параллельные запуски не конфликтовали
_RUN_ID = uuid.uuid4().hex[:8]
TEST_EMAIL    = f"pytest-kc-{_RUN_ID}@example.com"
TEST_PASSWORD = "TestPass1!"
TEST_FIRST    = "Pytest"
TEST_LAST     = "User"

ADMIN_EMAIL    = f"pytest-admin-{_RUN_ID}@example.com"
ADMIN_PASSWORD = "AdminPass1!"


# ---------------------------------------------------------------------------
# Проверка доступности — пропускаем всё если сервисы не запущены
# ---------------------------------------------------------------------------

def _check(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2).status_code == 200
    except Exception:
        return False


_SERVICES_UP = _check(f"{KC_BASE}/realms/{KC_REALM}/.well-known/openid-configuration") and \
               _check("http://localhost:8001/api/health")

pytestmark = pytest.mark.skipif(
    not _SERVICES_UP,
    reason="Keycloak или backend не запущен — пропускаем интеграционные тесты",
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _kc_token_url() -> str:
    return f"{KC_BASE}/realms/{KC_REALM}/protocol/openid-connect/token"


def _kc_admin_token() -> str:
    """Получить admin-токен из master realm."""
    resp = httpx.post(
        f"{KC_BASE}/realms/{KC_ADMIN_REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": KC_ADMIN_CLIENT,
            "username": KC_ADMIN_USER,
            "password": KC_ADMIN_PASS,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _delete_kc_user(email: str) -> None:
    """Удалить пользователя из Keycloak по email (игнорирует если нет)."""
    try:
        token = _kc_admin_token()
        resp = httpx.get(
            f"{KC_BASE}/admin/realms/{KC_REALM}/users",
            params={"email": email},
            headers={"Authorization": f"Bearer {token}"},
        )
        users = resp.json()
        for u in users:
            httpx.delete(
                f"{KC_BASE}/admin/realms/{KC_REALM}/users/{u['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception:
        pass


def _delete_pg_user(email: str) -> None:
    """Удалить пользователя из PostgreSQL через backend (нет прямого доступа — через docker exec)."""
    import subprocess
    subprocess.run(
        ["docker", "exec", "infrastructure-postgres-1",
         "psql", "-U", "astro", "-d", "astro_db",
         "-c", f"DELETE FROM users WHERE email='{email}';"],
        capture_output=True,
    )


def _assign_admin_role_in_kc(email: str) -> None:
    """Назначить роль 'admin' пользователю в Keycloak."""
    token = _kc_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    users = httpx.get(
        f"{KC_BASE}/admin/realms/{KC_REALM}/users",
        params={"email": email}, headers=headers,
    ).json()
    assert users, f"User {email} not found in Keycloak"
    user_id = users[0]["id"]

    role = httpx.get(
        f"{KC_BASE}/admin/realms/{KC_REALM}/roles/admin",
        headers=headers,
    ).json()

    httpx.post(
        f"{KC_BASE}/admin/realms/{KC_REALM}/users/{user_id}/role-mappings/realm",
        headers={**headers, "Content-Type": "application/json"},
        json=[{"id": role["id"], "name": "admin"}],
    )


def _get_user_token(email: str, password: str) -> str:
    resp = httpx.post(
        _kc_token_url(),
        data={
            "grant_type": "password",
            "client_id": KC_FRONTEND_CLIENT,
            "username": email,
            "password": password,
        },
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _sync(token: str) -> httpx.Response:
    return httpx.post(
        f"{BACKEND}/auth/sync",
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registered_user() -> Generator[dict, None, None]:
    """Регистрирует тестового пользователя, возвращает данные, удаляет после всех тестов."""
    resp = httpx.post(
        f"{BACKEND}/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "first_name": TEST_FIRST,
            "last_name": TEST_LAST,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    data = resp.json()
    yield data

    # Очистка
    _delete_kc_user(TEST_EMAIL)
    _delete_pg_user(TEST_EMAIL)


@pytest.fixture(scope="module")
def user_token(registered_user) -> str:
    """JWT токен зарегистрированного пользователя."""
    return _get_user_token(TEST_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def synced_user_token(user_token) -> str:
    """Токен после первого /auth/sync (пользователь есть в PostgreSQL)."""
    resp = _sync(user_token)
    assert resp.status_code == 200
    return user_token


@pytest.fixture(scope="module")
def admin_token(registered_user) -> Generator[str, None, None]:
    """Регистрирует отдельного admin-пользователя, возвращает токен, удаляет после модуля."""
    # Создаём через /register, потом назначаем роль admin
    resp = httpx.post(
        f"{BACKEND}/auth/register",
        json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "first_name": "Admin",
            "last_name": "User",
        },
    )
    assert resp.status_code == 201, f"Admin registration failed: {resp.text}"
    _assign_admin_role_in_kc(ADMIN_EMAIL)
    # Получаем новый токен (с ролью admin)
    token = _get_user_token(ADMIN_EMAIL, ADMIN_PASSWORD)
    # Синхронизируем в БД
    _sync(token)
    yield token

    # Очистка
    _delete_kc_user(ADMIN_EMAIL)
    _delete_pg_user(ADMIN_EMAIL)


# ---------------------------------------------------------------------------
# Тесты: Регистрация
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_new_user_returns_201(self, registered_user):
        assert "id" in registered_user
        assert registered_user["email"] == TEST_EMAIL
        assert registered_user["full_name"] == f"{TEST_FIRST} {TEST_LAST}"

    def test_register_duplicate_email_returns_409(self, registered_user):
        resp = httpx.post(
            f"{BACKEND}/auth/register",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_weak_password_too_short(self):
        resp = httpx.post(
            f"{BACKEND}/auth/register",
            json={"email": f"x-{_RUN_ID}@example.com", "password": "abc"},
        )
        assert resp.status_code == 422

    def test_register_weak_password_no_uppercase(self):
        resp = httpx.post(
            f"{BACKEND}/auth/register",
            json={"email": f"x-{_RUN_ID}@example.com", "password": "alllower1"},
        )
        assert resp.status_code == 422

    def test_register_weak_password_no_digit(self):
        resp = httpx.post(
            f"{BACKEND}/auth/register",
            json={"email": f"x-{_RUN_ID}@example.com", "password": "NoDigitHere"},
        )
        assert resp.status_code == 422

    def test_register_invalid_email(self):
        resp = httpx.post(
            f"{BACKEND}/auth/register",
            json={"email": "not-an-email", "password": TEST_PASSWORD},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Тесты: Keycloak-токен
# ---------------------------------------------------------------------------

class TestKeycloakToken:
    def test_can_login_with_registered_credentials(self, registered_user):
        token = _get_user_token(TEST_EMAIL, TEST_PASSWORD)
        assert len(token) > 100

    def test_token_has_user_role(self, user_token):
        import base64, json as _json
        parts = user_token.split(".")
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = _json.loads(base64.b64decode(padded))
        assert "user" in payload.get("realm_access", {}).get("roles", [])

    def test_token_has_correct_audience(self, user_token):
        import base64, json as _json
        parts = user_token.split(".")
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = _json.loads(base64.b64decode(padded))
        aud = payload.get("aud", [])
        if isinstance(aud, str):
            aud = [aud]
        assert "astro-backend" in aud

    def test_wrong_password_fails(self, registered_user):
        resp = httpx.post(
            _kc_token_url(),
            data={
                "grant_type": "password",
                "client_id": KC_FRONTEND_CLIENT,
                "username": TEST_EMAIL,
                "password": "WrongPass99!",
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Тесты: /auth/sync
# ---------------------------------------------------------------------------

class TestAuthSync:
    def test_sync_after_register_returns_existing_user(self, user_token):
        """/register уже создаёт запись в PostgreSQL, поэтому sync вернёт created=False."""
        resp = _sync(user_token)
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == TEST_EMAIL
        assert body["created"] is False
        assert "id" in body

    def test_second_sync_is_idempotent(self, synced_user_token):
        resp = _sync(synced_user_token)
        assert resp.status_code == 200
        assert resp.json()["created"] is False

    def test_sync_without_token_returns_403(self):
        resp = httpx.post(f"{BACKEND}/auth/sync")
        assert resp.status_code == 403

    def test_sync_with_invalid_token_returns_401(self):
        resp = httpx.post(
            f"{BACKEND}/auth/sync",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Тесты: /auth/me
# ---------------------------------------------------------------------------

class TestAuthMe:
    def test_me_returns_user_data(self, synced_user_token):
        resp = httpx.get(
            f"{BACKEND}/auth/me",
            headers={"Authorization": f"Bearer {synced_user_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == TEST_EMAIL
        assert body["is_active"] is True
        assert "id" in body
        assert "created_at" in body

    def test_me_without_token_returns_403(self):
        resp = httpx.get(f"{BACKEND}/auth/me")
        assert resp.status_code == 403

    def test_me_with_invalid_token_returns_401(self):
        resp = httpx.get(
            f"{BACKEND}/auth/me",
            headers={"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.invalid.sig"},
        )
        assert resp.status_code == 401

    def test_me_for_unsynced_user_returns_401(self):
        """Пользователь существует в Keycloak но НЕ в PostgreSQL → /auth/me должен вернуть 401."""
        # Создаём пользователя напрямую через Keycloak Admin API (минуя /register,
        # который автоматически синхронизирует в PostgreSQL)
        email = f"nosync-{_RUN_ID}@example.com"
        kc_user_id = None
        try:
            kc_token = _kc_admin_token()
            headers = {"Authorization": f"Bearer {kc_token}", "Content-Type": "application/json"}

            create_resp = httpx.post(
                f"{KC_BASE}/admin/realms/{KC_REALM}/users",
                headers=headers,
                json={
                    "username": email,
                    "email": email,
                    "firstName": "Nosync",
                    "lastName": "User",
                    "enabled": True,
                    "emailVerified": True,
                    "requiredActions": [],
                    "credentials": [{"type": "password", "value": TEST_PASSWORD, "temporary": False}],
                },
            )
            assert create_resp.status_code == 201, f"KCuser create failed: {create_resp.text}"
            kc_user_id = create_resp.headers["Location"].rstrip("/").split("/")[-1]

            # Назначаем роль 'user' чтобы токен прошёл audience check
            role = httpx.get(
                f"{KC_BASE}/admin/realms/{KC_REALM}/roles/user",
                headers={"Authorization": f"Bearer {kc_token}"},
            ).json()
            httpx.post(
                f"{KC_BASE}/admin/realms/{KC_REALM}/users/{kc_user_id}/role-mappings/realm",
                headers=headers,
                json=[{"id": role["id"], "name": "user"}],
            )

            token = _get_user_token(email, TEST_PASSWORD)
            resp = httpx.get(
                f"{BACKEND}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 401
            assert "sync" in resp.json()["detail"].lower()
        finally:
            if kc_user_id:
                _delete_kc_user(email)
            _delete_pg_user(email)


# ---------------------------------------------------------------------------
# Тесты: Защищённые эндпоинты (проекты)
# ---------------------------------------------------------------------------

class TestProtectedEndpoints:
    def test_projects_without_token_returns_403(self):
        resp = httpx.get(f"{BACKEND}/projects/")
        assert resp.status_code == 403

    def test_projects_with_valid_token_returns_200(self, synced_user_token):
        resp = httpx.get(
            f"{BACKEND}/projects/",
            headers={"Authorization": f"Bearer {synced_user_token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_projects_with_invalid_token_returns_401(self):
        resp = httpx.get(
            f"{BACKEND}/projects/",
            headers={"Authorization": "Bearer bad.token.value"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Тесты: /templates — публичный GET, запись только для admin
# ---------------------------------------------------------------------------

class TestTemplates:
    def test_get_templates_public(self):
        """GET /templates/ доступен без авторизации."""
        resp = httpx.get(f"{BACKEND}/templates/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_template_without_token_returns_403(self):
        resp = httpx.post(
            f"{BACKEND}/templates/",
            json={"name": "Test", "text_prompt": "prompt"},
        )
        assert resp.status_code == 403

    def test_create_template_user_role_returns_403(self, synced_user_token):
        """Роль 'user' не может создавать шаблоны."""
        resp = httpx.post(
            f"{BACKEND}/templates/",
            headers={"Authorization": f"Bearer {synced_user_token}"},
            json={"name": "Test", "text_prompt": "prompt"},
        )
        assert resp.status_code == 403
        assert "role" in resp.json()["detail"].lower()

    def test_create_template_admin_role_returns_201(self, admin_token):
        resp = httpx.post(
            f"{BACKEND}/templates/",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": f"T-{_RUN_ID}", "text_prompt": "Test prompt"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == f"T-{_RUN_ID}"
        assert "id" in body
        # Cleanup
        httpx.delete(
            f"{BACKEND}/templates/{body['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    def test_template_crud_full_cycle(self, admin_token):
        """Создание → GET → обновление → удаление."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        name = f"CRUD-{_RUN_ID}"

        # СОЗДАНИЕ
        create_resp = httpx.post(
            f"{BACKEND}/templates/",
            headers=headers,
            json={"name": name, "text_prompt": "original prompt"},
        )
        assert create_resp.status_code == 201
        template_id = create_resp.json()["id"]

        # GET list — шаблон присутствует
        list_resp = httpx.get(f"{BACKEND}/templates/")
        ids = [t["id"] for t in list_resp.json()]
        assert template_id in ids

        # ОБНОВЛЕНИЕ
        update_resp = httpx.put(
            f"{BACKEND}/templates/{template_id}",
            headers=headers,
            json={"name": f"{name}-updated", "text_prompt": "updated prompt"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == f"{name}-updated"

        # УДАЛЕНИЕ
        delete_resp = httpx.delete(
            f"{BACKEND}/templates/{template_id}",
            headers=headers,
        )
        assert delete_resp.status_code == 204

        # GET list — шаблон удалён
        list_resp2 = httpx.get(f"{BACKEND}/templates/")
        ids2 = [t["id"] for t in list_resp2.json()]
        assert template_id not in ids2

    def test_update_nonexistent_template_returns_404(self, admin_token):
        resp = httpx.put(
            f"{BACKEND}/templates/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "x", "text_prompt": "y"},
        )
        assert resp.status_code == 404

    def test_delete_nonexistent_template_returns_404(self, admin_token):
        resp = httpx.delete(
            f"{BACKEND}/templates/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Тесты: Проверка работоспособности (healthcheck)
# ---------------------------------------------------------------------------

class TestDeleteMe:
    def test_delete_me_without_token_returns_403(self):
        resp = httpx.delete(f"{BACKEND}/auth/me")
        assert resp.status_code == 403

    def test_delete_me_with_invalid_token_returns_401(self):
        resp = httpx.delete(
            f"{BACKEND}/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_delete_me_removes_user_from_keycloak_and_pg(self):
        """Регистрируем отдельного пользователя, удаляем через DELETE /auth/me,
        убеждаемся что нет ни в Keycloak, ни в PostgreSQL."""
        run_id = uuid.uuid4().hex[:8]
        email = f"pytest-del-{run_id}@example.com"
        password = "DelPass1!"

        # Регистрируем
        reg = httpx.post(
            f"{BACKEND}/auth/register",
            json={"email": email, "password": password, "first_name": "Del", "last_name": "Test"},
        )
        assert reg.status_code == 201, f"Register failed: {reg.text}"

        # Получаем токен и синхронизируем в PG
        token = _get_user_token(email, password)
        sync = _sync(token)
        assert sync.status_code == 200

        # Удаляем аккаунт
        del_resp = httpx.delete(
            f"{BACKEND}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 204, f"Delete failed: {del_resp.text}"

        # Пользователь должен исчезнуть из Keycloak
        kc_token = _kc_admin_token()
        kc_users = httpx.get(
            f"{KC_BASE}/admin/realms/{KC_REALM}/users",
            params={"email": email},
            headers={"Authorization": f"Bearer {kc_token}"},
        ).json()
        assert len(kc_users) == 0, f"User still in Keycloak: {kc_users}"

        # После удаления из Keycloak и PG старый JWT
        # не находит пользователя в базе → 401
        me_resp = httpx.get(
            f"{BACKEND}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 401

    def test_delete_me_is_idempotent_with_fresh_token(self, registered_user):
        """Нельзя удалить уже удалённый аккаунт — токен не выдаётся (401 от Keycloak)."""
        run_id = uuid.uuid4().hex[:8]
        email = f"pytest-del2-{run_id}@example.com"
        password = "DelPass1!"

        httpx.post(
            f"{BACKEND}/auth/register",
            json={"email": email, "password": password},
        )
        token = _get_user_token(email, password)
        _sync(token)

        # Первое удаление — успешно
        r1 = httpx.delete(f"{BACKEND}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 204

        # Второй DELETE с тем же JWT — пользователя нет ни в Keycloak ни в PG
        r2 = httpx.delete(f"{BACKEND}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code in (401, 404)


# ---------------------------------------------------------------------------
# Тесты: Проверка работоспособности (healthcheck)
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_healthy(self):
        resp = httpx.get("http://localhost:8001/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
