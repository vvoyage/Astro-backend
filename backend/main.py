from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, users, projects, assets, templates, snapshots, deployments
from app.api.v1.generation.router import router as generation_router
from app.api.v1.editor.router import router as editor_router
from app.core.config import settings
from app.core.dependencies import close_redis, init_redis
from app.core.logging import setup_logging
from app.db import models

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application")
    await init_redis()
    yield
    logger.info("Shutting down application")
    await close_redis()


def create_application() -> FastAPI:
    """Создаёт и настраивает экземпляр FastAPI."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        debug=settings.DEBUG,
        version=settings.VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    
    # PKCE для Swagger UI (нужно для Keycloak)
    application.swagger_ui_init_oauth = {
        "usePkceWithAuthorizationCodeGrant": True
    }
    
    # CORS — на prod надо будет сузить список origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    api_v1_prefix = "/api/v1"
    application.include_router(auth.router, prefix=api_v1_prefix)
    application.include_router(users.router, prefix=api_v1_prefix)
    application.include_router(projects.router, prefix=api_v1_prefix)
    application.include_router(assets.router, prefix=api_v1_prefix)
    application.include_router(templates.router, prefix=api_v1_prefix)
    application.include_router(snapshots.router, prefix=api_v1_prefix)
    application.include_router(deployments.router, prefix=api_v1_prefix)
    application.include_router(generation_router, prefix=api_v1_prefix)
    application.include_router(editor_router, prefix=api_v1_prefix)

    return application

app = create_application()

@app.get("/api/health")
async def health_check():
    """Просто проверка что апи живой."""
    return {"status": "healthy"}