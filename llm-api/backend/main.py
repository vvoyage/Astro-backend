from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import asyncio
from functools import partial
from typing import List, Optional

# Логирование
from backend.logger import setup_logging, get_logger
from backend.middleware import RequestLoggingMiddleware, get_request_id
from backend.llama_engine import get_llama_engine, GenerationError

# Настройка логирования при импорте модуля
setup_logging()
logger = get_logger("llm-api")
llama_engine = get_llama_engine()

app = FastAPI()

# Регистрация middleware для логирования запросов и Request ID
app.add_middleware(RequestLoggingMiddleware, service_name="llm-api")


class UsageInfo(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=16000, description="Prompt to send to Llama")
    max_tokens: Optional[int] = Field(
        None,
        ge=1,
        le=4096,
        description="Maximum number of new tokens to generate",
    )
    temperature: Optional[float] = Field(
        None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0 = deterministic)",
    )
    top_p: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling probability mass",
    )
    stop: Optional[List[str]] = Field(
        None,
        min_length=1,
        max_length=4,
        description="Optional stop sequences",
    )
    echo: bool = Field(False, description="If true, include prompt in the output")


class GenerateResponse(BaseModel):
    text: str
    finish_reason: Optional[str] = None
    usage: Optional[UsageInfo] = None


class ErrorResponse(BaseModel):
    detail: str


@app.post(
    "/generate/",
    response_model=GenerateResponse,
    responses={
        200: {"description": "Успешная генерация текста."},
        400: {
            "model": ErrorResponse,
            "description": "Ошибка в запросе (пустой prompt или неверные параметры)",
        },
        500: {
            "model": ErrorResponse,
            "description": "Внутренняя ошибка сервера",
        },
    },
    summary="Генерация текста через Llama",
    description="Универсальный эндпоинт для генерации текста с параметрами Llama.",
)
async def generate_text(req: Request, request_data: GenerateRequest):
    request_id = get_request_id(req)

    prompt = request_data.prompt.strip()
    if not prompt:
        logger.warning("generate_empty_prompt", request_id=request_id)
        raise HTTPException(status_code=400, detail="Prompt is empty.")

    if request_data.stop and any(not token for token in request_data.stop):
        logger.warning("generate_invalid_stop", request_id=request_id)
        raise HTTPException(status_code=400, detail="Stop sequences must be non-empty strings.")

    effective_max_tokens = request_data.max_tokens if request_data.max_tokens else llama_engine.max_tokens
    effective_temperature = request_data.temperature if request_data.temperature is not None else 0.7
    effective_top_p = request_data.top_p if request_data.top_p is not None else 0.9
    effective_stop = request_data.stop
    effective_echo = request_data.echo

    loop = asyncio.get_running_loop()
    generate_call = partial(
        llama_engine.generate,
        prompt,
        max_tokens=effective_max_tokens,
        temperature=effective_temperature,
        top_p=effective_top_p,
        stop=effective_stop,
        echo=effective_echo,
    )

    try:
        logger.info(
            "generate_started",
            request_id=request_id,
            has_stop=bool(effective_stop),
            echo=effective_echo,
            temperature=effective_temperature,
            top_p=effective_top_p,
            max_tokens=effective_max_tokens,
        )
        result = await loop.run_in_executor(None, generate_call)
    except GenerationError as exc:
        logger.error(
            "generate_failed",
            error=str(exc),
            request_id=request_id,
        )
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(exc)}")
    except Exception as e:
        logger.error(
            "generate_error",
            error=str(e),
            error_type=type(e).__name__,
            request_id=request_id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Internal processing error: {str(e)}")

    logger.info(
        "generate_completed",
        text_length=len(result["text"]),
        finish_reason=result.get("finish_reason"),
        request_id=request_id,
    )

    return GenerateResponse(
        text=result["text"],
        finish_reason=result.get("finish_reason"),
        usage=result.get("usage"),
    )




@app.get("/health/live")
async def liveness_probe():
    """
    Liveness probe - проверяет, что процесс жив.
    Возвращает статус "alive" если процесс запущен.
    """
    return JSONResponse(content={"status": "alive"})


@app.get("/health/ready")
async def readiness_probe():
    """
    Readiness probe - проверяет, что приложение готово обслуживать трафик.
    Модель загружается при старте приложения, поэтому всегда готова.
    """
    return JSONResponse(content={"status": "ready"})

