"""A0: OptimizerAgent — свободный текст ТЗ → структурированный JSON с подзадачами."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class OptimizerAgent(BaseAgent):
    """A0: принимает сырое ТЗ пользователя, возвращает JSON со структурированными подзадачами."""

    SYSTEM_PROMPT = """Ты — аналитик требований для генератора Astro-сайтов.
Преобразуй текстовое ТЗ пользователя в структурированный JSON.

ОБЯЗАТЕЛЬНЫЙ формат ответа — ТОЛЬКО JSON, без markdown, без комментариев:
{
  "title": "Название сайта",
  "description": "Краткое описание",
  "pages": [
    {
      "name": "index",
      "title": "Главная",
      "sections": ["hero", "about", "cta"]
    }
  ],
  "global_style": {
    "color_scheme": "minimalist",
    "primary_color": "#2C1810",
    "font": "sans-serif",
    "theme": "light"
  },
  "components": ["Button", "Nav", "Footer"],
  "features": ["адаптивный дизайн", "кнопка заказа"]
}"""

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        input_data: {"prompt": str, "template_slug": str | None}
        returns: {"pages": [...], "global_style": {...}, "components": [...]}
        """
        prompt = input_data.get("prompt", "")
        template_slug = input_data.get("template_slug")

        user_prompt = f"ТЗ пользователя: {prompt}"
        if template_slug:
            user_prompt += f"\nИспользуемый шаблон: {template_slug}"

        raw = await self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        return self._extract_json(raw)
