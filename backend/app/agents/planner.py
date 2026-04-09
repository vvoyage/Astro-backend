"""PlannerAgent: анализирует промпт + список файлов → план редактирования.

Используется перед _edit_all_files: вместо того чтобы гнать один промпт
через каждый файл по очереди, планировщик решает какие файлы вообще трогать
и формулирует точечную инструкцию для каждого.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """Возвращает {file_path: instruction} — только для файлов, которые надо менять."""

    SYSTEM_PROMPT = """\
Ты — планировщик редактирования Astro-сайта.
Тебе дают список исходных файлов проекта и задачу пользователя.
Определи, какие файлы нужно изменить и что именно сделать в каждом.

Верни ТОЛЬКО валидный JSON-объект вида:
{"путь/к/файлу.astro": "конкретная инструкция для этого файла", ...}

Правила:
- Включай только файлы, которые реально нужно изменить
- Инструкция для каждого файла — конкретная и самодостаточная (редактор видит только её, не общую задачу)
- Если задача глобальная (цвета всего сайта, типографика, layout) — включи все релевантные файлы
- Если задача точечная — включи только нужные файлы
- Никаких пояснений вне JSON"""

    async def plan(
        self,
        prompt: str,
        files: list[str],
        project_context: str = "",
    ) -> dict[str, str]:
        """Возвращает {file_path: instruction} для файлов, которые нужно изменить.

        При сбое парсинга возвращает пустой словарь — caller должен обработать fallback.
        """
        if not files:
            return {}

        files_list = "\n".join(f"- {f}" for f in files)
        user_prompt = (
            f"Файлы проекта:\n{files_list}\n\n"
            f"{'Контекст: ' + project_context + chr(10) + chr(10) if project_context else ''}"
            f"Задача: {prompt}"
        )
        raw = await self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        return self._parse_plan(raw, files)

    def _parse_plan(self, raw: str, valid_files: list[str]) -> dict[str, str]:
        """Парсит JSON-ответ агента, отфильтровывает несуществующие пути."""
        try:
            parsed = self._extract_json(raw)
        except Exception as exc:
            logger.warning("PlannerAgent: JSON parse failed: %s", exc)
            return {}
        if not isinstance(parsed, dict):
            logger.warning("PlannerAgent: expected dict, got %s", type(parsed))
            return {}
        valid_set = set(valid_files)
        plan = {
            k: str(v)
            for k, v in parsed.items()
            if k in valid_set and v
        }
        if not plan:
            logger.warning("PlannerAgent: plan is empty after filtering valid files")
        return plan

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        result = await self.plan(
            prompt=input_data["prompt"],
            files=input_data["files"],
            project_context=input_data.get("project_context", ""),
        )
        return {"plan": result}
