"""Работа с Keycloak Admin API — создание/удаление пользователей через service account."""
from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

_ADMIN_BASE = (
    f"{settings.KEYCLOAK_URL}/admin/realms/{settings.KEYCLOAK_REALM}"
)
_TOKEN_URL = (
    f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"
    "/protocol/openid-connect/token"
)
_USER_ROLE_NAME = "user"


async def _get_admin_token(client: httpx.AsyncClient) -> str:
    """Получить access_token через client_credentials (service account astro-backend)."""
    resp = await client.post(
        _TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": settings.KEYCLOAK_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
        },
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot obtain Keycloak admin token: {resp.text}",
        )
    return resp.json()["access_token"]


async def _get_user_role_id(client: httpx.AsyncClient, token: str) -> str:
    """Получить ID realm-роли 'user'."""
    resp = await client.get(
        f"{_ADMIN_BASE}/roles/{_USER_ROLE_NAME}",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot fetch role '{_USER_ROLE_NAME}': {resp.text}",
        )
    return resp.json()["id"]


async def create_keycloak_user(
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
) -> str:
    """Создать пользователя в Keycloak, назначить роль 'user'. Возвращает keycloak UUID (sub).

    Raises HTTPException 409 если email уже занят, 503 при недоступности Keycloak.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        token = await _get_admin_token(client)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Создаём пользователя
        create_resp = await client.post(
            f"{_ADMIN_BASE}/users",
            headers=headers,
            json={
                "username": email,
                "email": email,
                "firstName": first_name,
                "lastName": last_name,
                "enabled": True,
                "emailVerified": True,
                "requiredActions": [],
                "credentials": [
                    {"type": "password", "value": password, "temporary": False}
                ],
            },
        )

        if create_resp.status_code == 409:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        if create_resp.status_code != 201:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Keycloak user creation failed: {create_resp.text}",
            )

        # Получаем UUID нового пользователя из Location header
        location = create_resp.headers.get("Location", "")
        keycloak_id = location.rstrip("/").split("/")[-1]
        if not keycloak_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Keycloak did not return user Location header",
            )

        # Назначаем роль 'user'
        role_id = await _get_user_role_id(client, token)
        role_resp = await client.post(
            f"{_ADMIN_BASE}/users/{keycloak_id}/role-mappings/realm",
            headers=headers,
            json=[{"id": role_id, "name": _USER_ROLE_NAME}],
        )
        if role_resp.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to assign role: {role_resp.text}",
            )

        return keycloak_id


async def delete_keycloak_user(keycloak_id: str) -> None:
    """Удалить пользователя из Keycloak.

    Используется как для rollback при ошибке синхронизации, так и при
    явном удалении аккаунта через приложение.
    Удаление автоматически инвалидирует все активные сессии пользователя.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        token = await _get_admin_token(client)
        resp = await client.delete(
            f"{_ADMIN_BASE}/users/{keycloak_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code not in (200, 204, 404):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Keycloak user deletion failed: {resp.text}",
            )
