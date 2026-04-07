from typing import List, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, DbSession
from app.db.database import get_async_session
from app.db.models.project import Project as ProjectModel
from app.db.models.template import Template as TemplateModel
from app.schemas.project import ProjectCreate, Project, ProjectPreview
from app.services.storage import StorageService
from app.services.kubernetes import KubernetesService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/create-project", response_model=ProjectPreview)
async def create_project(
    project_data: ProjectCreate,
    user: CurrentUser,
    session: DbSession,
) -> ProjectPreview:
    """
    Создание нового проекта.
    1. Создает запись в БД
    2. Создает структуру в MinIO
    3. Генерирует проект через AI агентов
    4. Запускает сборку в Kubernetes
    5. Возвращает URL для предпросмотра
    """
    user_id = UUID(user["internal_user_id"])

    try:
        query = select(ProjectModel).where(
            ProjectModel.user_id == user_id,
            ProjectModel.name == project_data.name,
        )
        result = await session.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project with this name already exists",
            )

        prompt = None
        if project_data.template_id:
            template_query = select(TemplateModel).where(TemplateModel.id == project_data.template_id)
            result = await session.execute(template_query)
            template = result.scalar_one_or_none()
            if not template:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
            prompt = template.text_prompt
        else:
            prompt = project_data.prompt
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
            name=project_data.name,
            s3_path=f"projects/{user_id}/000",
            user_id=user_id,
            template_id=project_data.template_id,
            prompt=prompt,
        )
        session.add(db_project)
        await session.commit()
        await session.refresh(db_project)

        storage = StorageService()
        kubernetes = KubernetesService()

        try:
            await storage.cleanup_default_project(str(user_id))
            await storage.create_project_structure(user_id=str(user_id), project_id="000")

            try:
                await kubernetes.create_build_job(user_id=str(user_id), project_id="000")
            except Exception as k8s_error:
                print(f"Warning: Failed to create Kubernetes job: {k8s_error}")

            return ProjectPreview(
                project_id=db_project.id,
                path=f"projects/{user_id}/000/build/index.html",
            )

        except Exception as e:
            await session.delete(db_project)
            await session.commit()
            await storage.cleanup_default_project(str(user_id))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error initializing project infrastructure: {e}",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating project: {e}",
        )


@router.get("/", response_model=List[Project])
async def get_user_projects(
    user: CurrentUser,
    session: DbSession,
) -> List[ProjectModel]:
    """Получение списка проектов текущего пользователя."""
    user_id = UUID(user["internal_user_id"])
    result = await session.execute(
        select(ProjectModel).where(ProjectModel.user_id == user_id)
    )
    return result.scalars().all()


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> ProjectModel:
    """Получение конкретного проекта по ID (должен принадлежать текущему пользователю)."""
    user_id = UUID(user["internal_user_id"])
    result = await session.execute(
        select(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.user_id == user_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
