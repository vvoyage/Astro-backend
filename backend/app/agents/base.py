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

# TODO: from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Базовый класс для AI-агентов A0, A1, A2."""

    def __init__(self, model: str = "gpt-4o-mini", max_retries: int = 3) -> None:
        self.model = model
        self.max_retries = max_retries
        # TODO: self.client = AsyncOpenAI()

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Запустить агента и вернуть результат."""
        ...

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Вызов LLM с retry.

        TODO: реализовать через AsyncOpenAI с exponential backoff.
        """
        raise NotImplementedError

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Извлечь JSON из ответа LLM (обрабатывает markdown-обёртку)."""
        # Убираем ```json ... ``` если есть
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1)
        return json.loads(text)
