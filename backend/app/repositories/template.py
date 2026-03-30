"""Repository: CRUD операции с шаблонами промптов."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.template import Template


async def list_active(db: AsyncSession) -> list[Template]:
    result = await db.execute(
        select(Template).where(Template.is_active == True).order_by(Template.slug)  # noqa: E712
    )
    return list(result.scalars().all())


async def get_by_id(db: AsyncSession, template_id: UUID) -> Template | None:
    result = await db.execute(select(Template).where(Template.id == template_id))
    return result.scalar_one_or_none()


async def get_by_slug(db: AsyncSession, slug: str) -> Template | None:
    result = await db.execute(select(Template).where(Template.slug == slug))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, *, slug: str, name: str, prompt: str, **kwargs) -> Template:
    template = Template(slug=slug, name=name, prompt=prompt, **kwargs)
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template
