"""Projects API: список, получение, сохранение (000→уникальный), экспорт zip, удаление."""
from __future__ import annotations

import io
import urllib.parse
import zipfile
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import CurrentUser, DbSession
from app.db.models.project import Project as ProjectModel
from app.db.models.template import Template as TemplateModel
from app.schemas.project import Project, ProjectCreate, ProjectPreview, ProjectUpdate
from app.services.storage import StorageService

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Список
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[Project])
async def list_projects(
    user: CurrentUser,
    session: DbSession,
) -> List[ProjectModel]:
    """Возвращает все проекты текущего пользователя, от новых к старым."""
    user_id = UUID(user["internal_user_id"])
    result = await session.execute(
        select(ProjectModel)
        .where(ProjectModel.user_id == user_id)
        .order_by(ProjectModel.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Получение
# ---------------------------------------------------------------------------

@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> ProjectModel:
    """Возвращает один проект (должен принадлежать текущему пользователю)."""
    user_id = UUID(user["internal_user_id"])
    project = await _get_owned_project(session, project_id, user_id)
    return project


# ---------------------------------------------------------------------------
# Обновление
# ---------------------------------------------------------------------------

@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    user: CurrentUser,
    session: DbSession,
) -> ProjectModel:
    """Обновляет name и/или prompt проекта."""
    user_id = UUID(user["internal_user_id"])
    project = await _get_owned_project(session, project_id, user_id)

    if body.name is not None:
        # Проверка уникальности имени (исключая текущий проект)
        dup = await session.execute(
            select(ProjectModel).where(
                ProjectModel.user_id == user_id,
                ProjectModel.name == body.name,
                ProjectModel.id != project_id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project with this name already exists",
            )
        project.name = body.name  # type: ignore[assignment]

    if body.prompt is not None:
        project.prompt = body.prompt  # type: ignore[assignment]

    await session.flush()
    await session.refresh(project)
    return project


# ---------------------------------------------------------------------------
# Создание
# ---------------------------------------------------------------------------

@router.post("/", response_model=ProjectPreview, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: CurrentUser,
    session: DbSession,
) -> ProjectPreview:
    """Создаёт запись в БД и структуру MinIO во временном слоте ``000``.

    После этого вызовите ``POST /{project_id}/save``, чтобы перенести файлы на постоянный путь.
    """
    user_id = UUID(user["internal_user_id"])

    # Проверка на дублирование имени
    dup = await session.execute(
        select(ProjectModel).where(
            ProjectModel.user_id == user_id,
            ProjectModel.name == body.name,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project with this name already exists",
        )

    prompt: str | None = None
    if body.template_id:
        tmpl = await session.execute(
            select(TemplateModel).where(TemplateModel.id == body.template_id)
        )
        template = tmpl.scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        prompt = template.text_prompt
    else:
        prompt = body.prompt
        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either template_id or prompt must be provided",
            )

    if len(prompt) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt length cannot exceed 2000 characters",
        )

    db_project = ProjectModel(
        name=body.name,
        s3_path=f"projects/{user_id}/000",
        user_id=user_id,
        template_id=body.template_id,
        prompt=prompt,
    )
    session.add(db_project)
    await session.flush()
    await session.refresh(db_project)

    storage = StorageService()
    try:
        await storage.cleanup_default_project(str(user_id))
        await storage.create_project_structure(user_id=str(user_id), project_id="000")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error initializing project storage: {e}",
        )

    return ProjectPreview(
        project_id=db_project.id,
        path=f"projects/{user_id}/000/build/index.html",
    )


# ---------------------------------------------------------------------------
# Сохранение  (перенос из слота 000 в уникальный путь project_id)
# ---------------------------------------------------------------------------

@router.post("/{project_id}/save", response_model=Project)
async def save_project(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> ProjectModel:
    """Переносит файлы проекта из временного слота ``000`` в ``{project_id}`` в MinIO.

    Обновляет ``s3_path`` в БД — дальнейшие операции используют постоянный путь.
    Идемпотентно — если проект уже сохранён (s3_path != 000), просто возвращает его.
    """
    user_id = UUID(user["internal_user_id"])
    project = await _get_owned_project(session, project_id, user_id)

    tmp_path = f"projects/{user_id}/000"
    permanent_path = f"projects/{user_id}/{project_id}"

    if project.s3_path == tmp_path:
        storage = StorageService()
        try:
            await storage.copy_directory("projects", tmp_path, permanent_path)
            await storage.delete_directory("projects", tmp_path + "/")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error saving project files: {e}",
            )

        project.s3_path = permanent_path  # type: ignore[assignment]
        await session.flush()
        await session.refresh(project)

    return project


# ---------------------------------------------------------------------------
# Экспорт  (zip исходников)
# ---------------------------------------------------------------------------

@router.get("/{project_id}/export")
async def export_project(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> StreamingResponse:
    """Стримит ZIP-архив всех исходных файлов проекта."""
    user_id = UUID(user["internal_user_id"])
    project = await _get_owned_project(session, project_id, user_id)

    src_prefix = f"{project.s3_path}/src"
    storage = StorageService()

    try:
        file_paths = await storage.list_files("projects", src_prefix)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing project files: {e}",
        )

    if not file_paths:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No source files found for this project",
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in file_paths:
            if path.endswith("/"):
                continue  # пропускаем маркеры директорий
            try:
                data = await storage.get_file("projects", path)
                if data is not None:
                    # Убираем префикс проекта — в zip хранятся относительные пути
                    arc_name = path[len(project.s3_path):].lstrip("/")
                    zf.writestr(arc_name, data)
            except Exception:
                pass  # нечитаемые файлы пропускаем, не прерывая архивацию

    buf.seek(0)
    filename = f"{project.name or str(project_id)}.zip"
    # RFC 5987: filename*= позволяет передавать не-ASCII символы в заголовке
    filename_encoded = urllib.parse.quote(filename, safe="")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"},
    )


# ---------------------------------------------------------------------------
# Статус  (polling-альтернатива SSE)
# ---------------------------------------------------------------------------

class ProjectStatus(BaseModel):
    status: str
    preview_url: Optional[str]


@router.get("/{project_id}/status", response_model=ProjectStatus)
async def get_project_status(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> ProjectStatus:
    """Returns the current build status and preview URL for polling clients."""
    user_id = UUID(user["internal_user_id"])
    project = await _get_owned_project(session, project_id, user_id)

    preview_url: Optional[str] = None
    if project.s3_path and project.s3_path != "pending":
        preview_url = (
            f"{settings.MINIO_PUBLIC_URL}/astro-projects"
            f"/{project.s3_path}/build/index.html"
        )

    return ProjectStatus(status=project.status, preview_url=preview_url)


# ---------------------------------------------------------------------------
# Удаление
# ---------------------------------------------------------------------------

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_project(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Удаляет проект из PostgreSQL и удаляет все его файлы из MinIO."""
    user_id = UUID(user["internal_user_id"])
    project = await _get_owned_project(session, project_id, user_id)

    storage = StorageService()
    try:
        await storage.delete_directory("projects", project.s3_path + "/")
    except Exception:
        pass  # best-effort: удаляем из БД даже если MinIO вернул ошибку

    await session.delete(project)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _get_owned_project(session, project_id: UUID, user_id: UUID) -> ProjectModel:
    result = await session.execute(
        select(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.user_id == user_id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
