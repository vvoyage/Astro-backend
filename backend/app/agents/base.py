"""BaseAgent: общая логика для всех AI-агентов.

Содержит: формирование промпта, вызов LLM (AsyncOpenAI),
парсинг JSON из ответа, retry при ошибках, логирование.
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Базовый класс для AI-агентов A0, A1, A2."""

    def __init__(self, model: str = "gpt-4o-mini", max_retries: int = 3) -> None:
        self.model = model
        self.max_retries = max_retries
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,  # None → дефолтный api.openai.com
        )

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Запустить агента и вернуть результат."""
        ...

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Вызов LLM с exponential backoff retry (x3)."""
        logger.debug("[%s] Sending to LLM (model=%s):\n--- SYSTEM ---\n%s\n--- USER ---\n%s",
                     self.__class__.__name__, self.model, system_prompt.strip(), user_prompt[:500])
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM returned empty content")
        logger.info("[%s] LLM raw response:\n%s", self.__class__.__name__, content)
        return content

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Извлечь JSON из ответа LLM (обрабатывает markdown-обёртку и лишний текст)."""
        # 1. Markdown code block
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1)
        else:
            # 2. Bare JSON — strip everything before first { or [
            obj_start = text.find("{")
            arr_start = text.find("[")
            if obj_start == -1 and arr_start == -1:
                logger.error("No JSON found in LLM response: %s", text[:300])
                raise ValueError("No JSON object/array found in LLM response")
            if obj_start == -1:
                start = arr_start
            elif arr_start == -1:
                start = obj_start
            else:
                start = min(obj_start, arr_start)
            close = "}" if text[start] == "{" else "]"
            end = text.rfind(close)
            if end == -1:
                raise ValueError("Unmatched JSON bracket in LLM response")
            text = text[start : end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error: %s\nText was:\n%s", exc, text[:800])
            raise
