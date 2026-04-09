"""Unit-тесты для A4 EditorAgent.

Запуск:
    cd backend
    pytest tests/test_editor_agent.py -v
"""
import pytest
from unittest.mock import AsyncMock


# ---------------------------------------------------------------------------
# Хелпер
# ---------------------------------------------------------------------------

def _make_agent(llm_response: str):
    from app.agents.editor import EditorAgent
    agent = EditorAgent()
    agent._call_llm = AsyncMock(return_value=llm_response)
    return agent


# ---------------------------------------------------------------------------
# edit()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEditorAgentEdit:

    async def test_returns_llm_output_as_is(self):
        """edit() возвращает сырой ответ LLM без обработки."""
        new_code = "---\n---\n<h1>New Title</h1>"
        agent = _make_agent(new_code)
        result = await agent.edit(
            current_code="---\n---\n<h1>Old Title</h1>",
            element_id="hero-title",
            prompt="Замени заголовок на 'New Title'",
        )
        assert result == new_code

    async def test_current_code_in_prompt(self):
        """Текущий код файла попадает в user_prompt."""
        agent = _make_agent("updated code")
        current = "const x = 1;"
        await agent.edit(current_code=current, element_id="", prompt="что-то")
        _, user_prompt = agent._call_llm.call_args[0]
        assert current in user_prompt

    async def test_prompt_in_user_message(self):
        """Инструкция пользователя попадает в user_prompt."""
        agent = _make_agent("updated code")
        await agent.edit(
            current_code="code",
            element_id="",
            prompt="Сделай кнопку красной",
        )
        _, user_prompt = agent._call_llm.call_args[0]
        assert "Сделай кнопку красной" in user_prompt

    async def test_element_id_in_prompt_when_provided(self):
        """element_id упоминается в user_prompt, если передан."""
        agent = _make_agent("code")
        await agent.edit(
            current_code="code",
            element_id="cta-button",
            prompt="Изменить цвет",
        )
        _, user_prompt = agent._call_llm.call_args[0]
        assert "cta-button" in user_prompt

    async def test_element_id_absent_when_empty(self):
        """Если element_id пустой — в промпте нет слова 'элемент'."""
        agent = _make_agent("code")
        await agent.edit(current_code="code", element_id="", prompt="что-то")
        _, user_prompt = agent._call_llm.call_args[0]
        assert "элемент:" not in user_prompt

    async def test_project_context_in_prompt(self):
        """project_context попадает в user_prompt."""
        agent = _make_agent("code")
        await agent.edit(
            current_code="code",
            element_id="",
            prompt="изменить",
            project_context="Лендинг для кофейни",
        )
        _, user_prompt = agent._call_llm.call_args[0]
        assert "Лендинг для кофейни" in user_prompt

    async def test_project_context_absent_when_empty(self):
        """Если project_context пустой — в промпте нет 'Контекст проекта'."""
        agent = _make_agent("code")
        await agent.edit(current_code="code", element_id="", prompt="что-то")
        _, user_prompt = agent._call_llm.call_args[0]
        assert "Контекст проекта" not in user_prompt

    async def test_uses_edit_system_prompt(self):
        """edit() использует SYSTEM_PROMPT, а не FIX_SYSTEM_PROMPT."""
        from app.agents.editor import EditorAgent
        agent = _make_agent("code")
        await agent.edit(current_code="code", element_id="", prompt="что-то")
        system_prompt, _ = agent._call_llm.call_args[0]
        assert "ошибк" not in system_prompt.lower()
        assert "только полный" in system_prompt.lower() or "верни только" in system_prompt.lower()


# ---------------------------------------------------------------------------
# fix_build_error()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEditorAgentFixBuildError:

    async def test_returns_fixed_code(self):
        fixed = "const x: number = 1;"
        agent = _make_agent(fixed)
        result = await agent.fix_build_error(
            edited_code="const x = 1",
            stderr="Type error: ...",
            prompt="Добавь типы",
        )
        assert result == fixed

    async def test_stderr_in_prompt(self):
        """Текст ошибки сборки попадает в user_prompt."""
        agent = _make_agent("fixed code")
        await agent.fix_build_error(
            edited_code="code",
            stderr="Cannot find module 'foo'",
            prompt="изменить",
        )
        _, user_prompt = agent._call_llm.call_args[0]
        assert "Cannot find module 'foo'" in user_prompt

    async def test_edited_code_in_prompt(self):
        """Редактированный код попадает в user_prompt."""
        agent = _make_agent("fixed code")
        await agent.fix_build_error(
            edited_code="const broken = ;",
            stderr="SyntaxError",
            prompt="изменить",
        )
        _, user_prompt = agent._call_llm.call_args[0]
        assert "const broken = ;" in user_prompt

    async def test_original_prompt_in_prompt(self):
        """Исходная задача попадает в user_prompt."""
        agent = _make_agent("fixed code")
        await agent.fix_build_error(
            edited_code="code",
            stderr="error",
            prompt="Переверстай хедер",
        )
        _, user_prompt = agent._call_llm.call_args[0]
        assert "Переверстай хедер" in user_prompt

    async def test_uses_fix_system_prompt(self):
        """fix_build_error() использует FIX_SYSTEM_PROMPT."""
        agent = _make_agent("fixed code")
        await agent.fix_build_error(edited_code="code", stderr="err", prompt="p")
        system_prompt, _ = agent._call_llm.call_args[0]
        assert "ошибк" in system_prompt.lower()


# ---------------------------------------------------------------------------
# run() — совместимость с BaseAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEditorAgentRun:

    async def test_run_delegates_to_edit(self):
        """run() возвращает {'content': <результат edit()>}."""
        new_code = "<h1>New</h1>"
        agent = _make_agent(new_code)
        result = await agent.run({
            "current_code": "<h1>Old</h1>",
            "element_id": "title",
            "prompt": "Обнови заголовок",
        })
        assert result == {"content": new_code}

    async def test_run_optional_fields_have_defaults(self):
        """run() работает без element_id и project_context."""
        agent = _make_agent("code")
        result = await agent.run({
            "current_code": "some code",
            "prompt": "Сделай что-нибудь",
        })
        assert "content" in result
