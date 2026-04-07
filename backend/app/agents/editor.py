"""A4 EditorAgent: редактирует один файл по prompt пользователя, возвращает полный код."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class EditorAgent(BaseAgent):
    """A4: принимает текущий код файла + prompt, возвращает полный обновлённый код."""

    SYSTEM_PROMPT = """\
Ты — разработчик Astro-сайтов. Тебе дают текущий код файла и задачу по его изменению.
Верни ТОЛЬКО полный обновлённый код файла — без объяснений, без markdown-обёртки,
без тегов вроде ```astro или ```typescript. Только сам код.
Сохраняй все части файла, которые не затронуты правкой."""

    FIX_SYSTEM_PROMPT = """\
Ты — разработчик Astro-сайтов. Сборка проекта завершилась с ошибкой.
Тебе дают код файла, текст ошибки и исходную задачу.
Верни ТОЛЬКО полный исправленный код файла — без объяснений и markdown-обёртки."""

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Базовый run для совместимости с BaseAgent. Используется edit() напрямую."""
        code = await self.edit(
            current_code=input_data["current_code"],
            element_id=input_data.get("element_id", ""),
            prompt=input_data["prompt"],
            project_context=input_data.get("project_context", ""),
        )
        return {"content": code}

    async def edit(
        self,
        current_code: str,
        element_id: str,
        prompt: str,
        project_context: str = "",
    ) -> str:
        """Редактирует файл и возвращает полный обновлённый код.

        Args:
            current_code: текущее содержимое файла
            element_id: идентификатор элемента / компонента для уточнения контекста
            prompt: задача от пользователя
            project_context: краткое описание проекта (необязательно)
        """
        user_prompt = (
            f"Файл{f' (элемент: {element_id})' if element_id else ''}:\n"
            f"```\n{current_code}\n```\n\n"
            f"{'Контекст проекта: ' + project_context + chr(10) + chr(10) if project_context else ''}"
            f"Задача: {prompt}"
        )
        return await self._call_llm(self.SYSTEM_PROMPT, user_prompt)

    async def fix_build_error(
        self,
        edited_code: str,
        stderr: str,
        prompt: str,
    ) -> str:
        """Повторная правка файла с учётом ошибки сборки.

        Args:
            edited_code: код после предыдущего вызова edit()
            stderr: вывод ошибки сборки
            prompt: исходная задача пользователя
        """
        user_prompt = (
            f"Код файла:\n```\n{edited_code}\n```\n\n"
            f"Ошибка сборки:\n```\n{stderr}\n```\n\n"
            f"Исходная задача: {prompt}"
        )
        return await self._call_llm(self.FIX_SYSTEM_PROMPT, user_prompt)
