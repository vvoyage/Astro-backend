from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import DbSession, require_role
from app.repositories import template as template_repo
from app.schemas.template import Template, TemplateCreate, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/", response_model=List[Template])
async def get_templates(
    session: DbSession,
) -> list:
    """Получение списка активных шаблонов. Публичный эндпоинт."""
    return await template_repo.list_active(session)


@router.post("/", response_model=Template, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    session: DbSession,
    _: Annotated[dict, Depends(require_role("admin"))],
) -> object:
    """Создать шаблон. Только для admin."""
    template = await template_repo.create(
        session,
        slug=data.slug,
        name=data.name,
        text_prompt=data.text_prompt,
        description=data.description,
        is_active=data.is_active,
    )
    await session.commit()
    await session.refresh(template)
    return template


@router.put("/{template_id}", response_model=Template)
async def update_template(
    template_id: UUID,
    data: TemplateUpdate,
    session: DbSession,
    _: Annotated[dict, Depends(require_role("admin"))],
) -> object:
    """Обновить шаблон. Только для admin."""
    template = await template_repo.get_by_id(session, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    template = await template_repo.update(
        session,
        template,
        slug=data.slug,
        name=data.name,
        text_prompt=data.text_prompt,
        description=data.description,
        is_active=data.is_active,
    )
    await session.commit()
    await session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    session: DbSession,
    _: Annotated[dict, Depends(require_role("admin"))],
) -> None:
    """Удалить шаблон. Только для admin."""
    template = await template_repo.get_by_id(session, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await template_repo.delete(session, template)
    await session.commit()
