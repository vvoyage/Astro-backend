from fastapi import FastAPI
from app.core.config import settings
from app.api.v1 import auth, users, projects, assets, templates, snapshots, deployments

def create_application() -> FastAPI:
    """
    Фабричная функция для создания экземпляра FastAPI
    
    Returns:
        FastAPI: Настроенное приложение FastAPI
    """
    application = FastAPI(
        title=settings.PROJECT_NAME,
        debug=settings.DEBUG,
        version=settings.VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json"
    )
    
    # Подключаем все роутеры
    api_v1_prefix = "/api/v1"
    application.include_router(auth.router, prefix=api_v1_prefix)
    application.include_router(users.router, prefix=api_v1_prefix)
    application.include_router(projects.router, prefix=api_v1_prefix)
    application.include_router(assets.router, prefix=api_v1_prefix)
    application.include_router(templates.router, prefix=api_v1_prefix)
    application.include_router(snapshots.router, prefix=api_v1_prefix)
    application.include_router(deployments.router, prefix=api_v1_prefix)

    return application

app = create_application()

@app.get("/api/health")
async def health_check():
    """
    Эндпоинт для проверки работоспособности API
    """
    return {"status": "healthy"} 