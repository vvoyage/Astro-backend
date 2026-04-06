"""A2: CodeGeneratorAgent — спецификация файлов → готовый код каждого файла."""
from __future__ import annotations

import json
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
        """
        file_spec = input_data["file"]
        project_spec = input_data.get("project_spec", {})

        user_prompt = (
            f"Файл для генерации: {json.dumps(file_spec, ensure_ascii=False)}\n"
            f"Контекст проекта: {json.dumps(project_spec, ensure_ascii=False, indent=2)}"
        )

        content = await self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        return {"path": file_spec["path"], "content": content}
