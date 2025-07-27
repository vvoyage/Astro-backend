from typing import List, Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth.dependencies import get_current_active_user
from app.db.database import get_async_session
from app.db.models.user import User
from app.db.models.project import Project as ProjectModel
from app.db.models.template import Template as TemplateModel
from app.schemas.project import ProjectCreate, Project, ProjectPreview
from app.services.storage import StorageService
from app.services.kubernetes import KubernetesService  
from app.services.project_generator import ProjectGenerationService 

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

@router.post("/create-project", response_model=ProjectPreview)
async def create_project(
    project_data: ProjectCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)]
) -> ProjectPreview:
    """
    Создание нового проекта.
    1. Создает запись в БД
    2. Создает структуру в MinIO
    3. Генерирует проект через AI агентов
    4. Запускает сборку в Kubernetes
    5. Возвращает URL для предпросмотра
    """
    try:
        # Проверяем существование проекта с таким именем
        query = select(ProjectModel).where(
            ProjectModel.user_id == current_user.id,
            ProjectModel.name == project_data.name
        )
        result = await session.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project with this name already exists"
            )
        
        # Определяем промпт
        prompt = None
        if project_data.template_id:
            template_query = select(TemplateModel).where(TemplateModel.id == project_data.template_id)
            result = await session.execute(template_query)
            template = result.scalar_one_or_none()
            
            if not template:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Template not found"
                )
            
            prompt = template.text_prompt
        else:
            prompt = project_data.prompt
            if not prompt:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either template_id or prompt must be provided"
                )

        # Проверяем длину промпта
        if len(prompt) > 2000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt length cannot exceed 2000 characters"
            )
        
        # Создаем проект с временным ID "000"
        db_project = ProjectModel(
            name=project_data.name,
            s3_path=f"projects/{current_user.id}/000",
            user_id=current_user.id,
            template_id=project_data.template_id,
            prompt=prompt
        )
        
        session.add(db_project)
        await session.commit()
        await session.refresh(db_project)

        # Инициализация сервисов
        storage = StorageService()
        project_generator = ProjectGenerationService()
        kubernetes = KubernetesService()
        
        try:
            # Очистка предыдущего временного проекта
            await storage.cleanup_default_project(str(current_user.id))

            # Создание структуры в MinIO
            await storage.create_project_structure(
                user_id=str(current_user.id),
                project_id="000"
            )

            # Запускаем генерацию проекта
            generation_success = await project_generator.generate_project(
                user_id=str(current_user.id),
                project_id="000",
                prompt=prompt
            )
            
            if not generation_success:
                raise Exception("Failed to generate project")

            try:
                # Запускаем сборку в Kubernetes
                job_name = await kubernetes.create_build_job(
                    user_id=str(current_user.id),
                    project_id="000"
                )
            except Exception as k8s_error:
                print(f"Warning: Failed to create Kubernetes job: {str(k8s_error)}")
                # Не прерываем выполнение, так как проект уже сгенерирован

            # Возврат информации для предпросмотра
            return ProjectPreview(
                project_id=db_project.id,
                path=f"projects/{current_user.id}/000/build/index.html",
                status="generated"  # Меняем статус, так как сборка может не запуститься
            )

        except Exception as e:
            # Если что-то пошло не так, удаляем проект из БД и очищаем MinIO
            await session.delete(db_project)
            await session.commit()
            await storage.cleanup_default_project(str(current_user.id))
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error initializing project infrastructure: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating project: {str(e)}"
        )

@router.get("/", response_model=List[Project])
async def get_user_projects(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)]
) -> List[ProjectModel]:
    """
    Получение списка проектов текущего пользователя.
    """
    query = select(ProjectModel).where(ProjectModel.user_id == current_user.id)
    result = await session.execute(query)
    return result.scalars().all()

@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)]
) -> ProjectModel:
    """
    Получение конкретного проекта по ID.
    Проект должен принадлежать текущему пользователю.
    """
    query = select(ProjectModel).where(
        ProjectModel.id == project_id,
        ProjectModel.user_id == current_user.id
    )
    result = await session.execute(query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project

