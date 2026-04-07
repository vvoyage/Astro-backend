from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.db.models.template import Template as TemplateModel
from app.schemas.template import Template, TemplateCreate, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/", response_model=List[Template])
async def get_templates(
    session: DbSession,
) -> List[TemplateModel]:
    """Получение списка всех доступных шаблонов. Публичный эндпоинт."""
    result = await session.execute(select(TemplateModel))
    return result.scalars().all()


@router.post("/", response_model=Template, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    session: DbSession,
    _: Annotated[dict, Depends(require_role("admin"))],
) -> TemplateModel:
    """Создать шаблон. Только для admin."""
    template = TemplateModel(name=data.name, text_prompt=data.text_prompt)
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@router.put("/{template_id}", response_model=Template)
async def update_template(
    template_id: UUID,
    data: TemplateUpdate,
    session: DbSession,
    _: Annotated[dict, Depends(require_role("admin"))],
) -> TemplateModel:
    """Обновить шаблон. Только для admin."""
    result = await session.execute(select(TemplateModel).where(TemplateModel.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    template.name = data.name
    template.text_prompt = data.text_prompt
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
    result = await session.execute(select(TemplateModel).where(TemplateModel.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await session.delete(template)
    await session.commit()
