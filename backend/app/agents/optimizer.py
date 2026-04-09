"""A0 OptimizerAgent: парсит свободный текст пользователя в структурированный JSON для A1."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class OptimizerAgent(BaseAgent):
    """A0: из сырого ТЗ делает структурированный JSON — pages, components, стиль и т.д."""

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
        """input_data: {"prompt": str, "template_slug": str | None}."""
        prompt = input_data.get("prompt", "")
        template_slug = input_data.get("template_slug")

        user_prompt = f"ТЗ пользователя: {prompt}"
        if template_slug:
            user_prompt += f"\nИспользуемый шаблон: {template_slug}"

        raw = await self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        return self._extract_json(raw)
