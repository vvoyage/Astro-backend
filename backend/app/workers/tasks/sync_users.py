"""Периодическая задача: удаление из PostgreSQL пользователей, которых нет в Keycloak.

Запускается по расписанию через Celery Beat каждые 10 минут.
Сценарий: администратор удалил пользователя через Keycloak UI —
задача обнаруживает это и каскадно очищает данные из PG.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import settings
from app.db.database import AsyncSessionFactory, engine
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_ADMIN_BASE = f"{settings.KEYCLOAK_URL}/admin/realms/{settings.KEYCLOAK_REALM}"
_TOKEN_URL = (
    f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"
    "/protocol/openid-connect/token"
)


@celery_app.task(name="sync_users.purge_deleted_keycloak_users")
def purge_deleted_keycloak_users() -> dict:
    """Сверяет пользователей PostgreSQL с Keycloak и удаляет лишних."""
    asyncio.run(engine.dispose())
    return asyncio.run(_sync())


# ---------------------------------------------------------------------------
# Асинхронная реализация
# ---------------------------------------------------------------------------

async def _get_admin_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        _TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": settings.KEYCLOAK_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _user_exists_in_keycloak(
    client: httpx.AsyncClient, token: str, keycloak_id: str
) -> bool:
    resp = await client.get(
        f"{_ADMIN_BASE}/users/{keycloak_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.status_code == 200


async def _sync() -> dict:
    from sqlalchemy import delete as sql_delete, select

    from app.db.models.asset import Asset
    from app.db.models.deployment import Deployment
    from app.db.models.project import Project
    from app.db.models.snapshot import Snapshot
    from app.db.models.user import User

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(User.id, User.keycloak_id, User.email)
            .where(User.keycloak_id.isnot(None))
        )
        users = result.all()

    if not users:
        logger.info("sync_users: no users with keycloak_id found, skipping")
        return {"checked": 0, "purged": 0}

    purged = 0
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            token = await _get_admin_token(http)

            for user_id, keycloak_id, email in users:
                exists = await _user_exists_in_keycloak(http, token, keycloak_id)
                if exists:
                    continue

                logger.info(
                    "sync_users: keycloak_id=%s (email=%s) not found in Keycloak — purging from DB",
                    keycloak_id,
                    email,
                )
                async with AsyncSessionFactory() as session:
                    # Каскадное удаление в правильном порядке (FK без ondelete)
                    project_ids_result = await session.execute(
                        select(Project.id).where(Project.user_id == user_id)
                    )
                    project_ids = [row[0] for row in project_ids_result.all()]

                    if project_ids:
                        await session.execute(
                            sql_delete(Asset).where(Asset.project_id.in_(project_ids))
                        )
                        await session.execute(
                            sql_delete(Snapshot).where(Snapshot.project_id.in_(project_ids))
                        )
                        await session.execute(
                            sql_delete(Deployment).where(Deployment.project_id.in_(project_ids))
                        )
                        await session.execute(
                            sql_delete(Project).where(Project.id.in_(project_ids))
                        )

                    await session.execute(sql_delete(User).where(User.id == user_id))
                    await session.commit()

                purged += 1

    except httpx.HTTPError as exc:
        logger.error("sync_users: Keycloak is unreachable: %s", exc)
        return {"checked": len(users), "purged": purged, "error": str(exc)}

    logger.info("sync_users: checked=%d purged=%d", len(users), purged)
    return {"checked": len(users), "purged": purged}
