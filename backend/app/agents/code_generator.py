"""A2: CodeGeneratorAgent — спецификация файлов → готовый код каждого файла."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class CodeGeneratorAgent(BaseAgent):
    """A2: генерирует код для каждого файла по спецификации от A1."""

    SYSTEM_PROMPT = """
    Ты — разработчик Astro-сайтов.
    Напиши код файла по заданной спецификации. Используй Astro, TypeScript, Tailwind CSS.
    Выведи ТОЛЬКО код файла без пояснений.
    """

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        input_data: {"file": {"path": str, "description": str}, "project_spec": {...}}
        returns: {"path": str, "content": str}

        TODO: реализовать вызов LLM через self._call_llm()
        """
        raise NotImplementedError("CodeGeneratorAgent.run() не реализован")
