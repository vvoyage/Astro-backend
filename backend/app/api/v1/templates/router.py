from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.db.models.template import Template as TemplateModel
from app.schemas.template import Template

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])

@router.get("/", response_model=List[Template])
async def get_templates(
    session: AsyncSession = Depends(get_async_session)
) -> List[TemplateModel]:
    """
    Получение списка всех доступных шаблонов.
    Шаблоны содержат готовые промпты для создания проектов.
    """
    query = select(TemplateModel)
    result = await session.execute(query)
    return result.scalars().all()