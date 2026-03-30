"""A0: OptimizerAgent — свободный текст ТЗ → структурированный JSON с подзадачами."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class OptimizerAgent(BaseAgent):
    """A0: принимает сырое ТЗ пользователя, возвращает JSON со структурированными подзадачами."""

    SYSTEM_PROMPT = """
    Ты — аналитик требований для генератора Astro-сайтов.
    Преобразуй текстовое ТЗ пользователя в структурированный JSON.
    Выведи ТОЛЬКО валидный JSON без комментариев.
    """

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        input_data: {"prompt": str, "template_slug": str | None}
        returns: {"pages": [...], "global_style": {...}, "components": [...]}

        TODO: реализовать вызов LLM через self._call_llm()
        """
        raise NotImplementedError("OptimizerAgent.run() не реализован")
