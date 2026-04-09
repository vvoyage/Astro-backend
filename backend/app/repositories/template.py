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


async def create(
    db: AsyncSession,
    *,
    slug: str,
    name: str,
    text_prompt: str,
    description: str | None = None,
    is_active: bool = True,
) -> Template:
    template = Template(
        slug=slug,
        name=name,
        text_prompt=text_prompt,
        description=description,
        is_active=is_active,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def update(
    db: AsyncSession,
    template: Template,
    *,
    slug: str | None = None,
    name: str | None = None,
    text_prompt: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> Template:
    if slug is not None:
        template.slug = slug
    if name is not None:
        template.name = name
    if text_prompt is not None:
        template.text_prompt = text_prompt
    if description is not None:
        template.description = description
    if is_active is not None:
        template.is_active = is_active
    await db.flush()
    await db.refresh(template)
    return template


async def delete(db: AsyncSession, template: Template) -> None:
    await db.delete(template)
    await db.flush()
