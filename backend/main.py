from fastapi import FastAPI
from app.core.config import settings

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
    
    return application

app = create_application()

@app.get("/api/health")
async def health_check():
    """
    Эндпоинт для проверки работоспособности API
    """
    return {"status": "healthy"} 