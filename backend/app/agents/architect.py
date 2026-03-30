"""A1: ArchitectAgent — подзадачи из A0 → JSON-спецификация файловой структуры проекта."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class ArchitectAgent(BaseAgent):
    """A1: принимает подзадачи от A0, возвращает полную спецификацию Astro-проекта."""

    SYSTEM_PROMPT = """
    Ты — архитектор Astro-проектов.
    По заданным подзадачам создай полную спецификацию файловой структуры проекта.
    Выведи ТОЛЬКО валидный JSON без комментариев.
    """

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        input_data: результат OptimizerAgent
        returns: {"files": [{"path": str, "description": str, "dependencies": [...]}]}

        TODO: реализовать вызов LLM через self._call_llm()
        """
        raise NotImplementedError("ArchitectAgent.run() не реализован")
