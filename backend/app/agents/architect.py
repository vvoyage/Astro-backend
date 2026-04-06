"""A1: ArchitectAgent — подзадачи из A0 → JSON-спецификация файловой структуры проекта."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ArchitectAgent(BaseAgent):
    """A1: принимает подзадачи от A0, возвращает полную спецификацию Astro-проекта."""

    SYSTEM_PROMPT = """Ты — архитектор Astro-проектов.
По заданным подзадачам создай полную спецификацию файловой структуры проекта.

ОБЯЗАТЕЛЬНЫЙ формат ответа — ТОЛЬКО JSON, без markdown, без комментариев:
{
  "files": [
    {
      "path": "src/pages/index.astro",
      "description": "Главная страница сайта",
      "content_hint": "Hero-секция, секция с описанием, кнопка CTA",
      "dependencies": ["src/components/Button.astro", "src/layouts/Layout.astro"]
    },
    {
      "path": "src/layouts/Layout.astro",
      "description": "Базовый layout с head и nav",
      "content_hint": "HTML5 структура, подключение Tailwind, мета-теги",
      "dependencies": []
    },
    {
      "path": "src/components/Button.astro",
      "description": "Переиспользуемая кнопка",
      "content_hint": "Tailwind стили, hover-эффект, slot для текста",
      "dependencies": []
    }
  ]
}

ТРЕБОВАНИЯ:
- Массив files НИКОГДА не должен быть пустым — минимум 3 файла
- Всегда включай src/pages/index.astro и src/layouts/Layout.astro
- Указывай реальные пути в Astro-проекте (src/pages/, src/components/, src/layouts/)
- content_hint должен описывать конкретное содержимое файла"""

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        input_data: результат OptimizerAgent
        returns: {"files": [{"path": str, "description": str, "content_hint": str, "dependencies": [...]}]}
        """
        user_prompt = f"Спецификация проекта:\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"
        raw = await self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        result = self._extract_json(raw)
        files = result.get("files", [])
        logger.info("A1 planned %d files: %s", len(files), [f.get("path") for f in files])
        return result
