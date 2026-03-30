"""Эндпоинты редактора: AI-редактирование элементов и прямое обновление файлов."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.editor import EditElementRequest, EditElementResponse, UpdateFileRequest

router = APIRouter(prefix="/editor", tags=["editor"])


@router.post("/edit", response_model=EditElementResponse)
async def edit_element(
    body: EditElementRequest,
    db: DbSession,
    user: CurrentUser,
) -> EditElementResponse:
    """AI-редактирование выбранного элемента по текстовой инструкции.

    TODO:
    1. Загрузить текущий файл из MinIO
    2. Вызвать LLM с контекстом элемента + инструкцией
    3. Сохранить обновлённый файл в MinIO
    4. Создать снапшот через repositories.snapshot.create()
    5. Вернуть новый контент файла
    """
    raise NotImplementedError


@router.get("/file")
async def get_file_code(
    project_id: str,
    file_path: str,
    user: CurrentUser,
) -> dict:
    """Вернуть исходный код файла проекта из MinIO.

    TODO: загрузить через services.storage
    """
    raise NotImplementedError


@router.put("/file")
async def update_file_code(
    body: UpdateFileRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Ручное обновление файла (без AI), создаёт снапшот.

    TODO: сохранить в MinIO + создать снапшот
    """
    raise NotImplementedError
