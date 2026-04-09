"""Unit-тесты для PlannerAgent.

Запуск:
    cd backend
    pytest tests/test_planner_agent.py -v
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Вспомогательная фабрика
# ---------------------------------------------------------------------------

def _make_planner(llm_response: str):
    """Создаёт PlannerAgent с замоканным _call_llm."""
    from app.agents.planner import PlannerAgent
    agent = PlannerAgent.__new__(PlannerAgent)
    agent.model = "test-model"
    agent.max_retries = 1
    agent._call_llm = AsyncMock(return_value=llm_response)
    return agent


FILES = [
    "pages/index.astro",
    "components/Header.astro",
    "components/Footer.astro",
    "layouts/Base.astro",
]


# ---------------------------------------------------------------------------
# _parse_plan
# ---------------------------------------------------------------------------

class TestParsePlan:

    def test_valid_json_returns_matching_files(self):
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent.__new__(PlannerAgent)
        raw = json.dumps({
            "components/Header.astro": "Сделай заголовок синим",
            "components/Footer.astro": "Сделай кнопку красной",
        })
        result = agent._parse_plan(raw, FILES)
        assert result == {
            "components/Header.astro": "Сделай заголовок синим",
            "components/Footer.astro": "Сделай кнопку красной",
        }

    def test_unknown_files_are_filtered_out(self):
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent.__new__(PlannerAgent)
        raw = json.dumps({
            "components/Header.astro": "change it",
            "nonexistent/ghost.astro": "do something",
        })
        result = agent._parse_plan(raw, FILES)
        assert "nonexistent/ghost.astro" not in result
        assert "components/Header.astro" in result

    def test_invalid_json_returns_empty_dict(self):
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent.__new__(PlannerAgent)
        result = agent._parse_plan("this is not json at all", FILES)
        assert result == {}

    def test_non_dict_json_returns_empty_dict(self):
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent.__new__(PlannerAgent)
        result = agent._parse_plan('["list", "not", "dict"]', FILES)
        assert result == {}

    def test_empty_instruction_values_are_filtered(self):
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent.__new__(PlannerAgent)
        raw = json.dumps({
            "components/Header.astro": "valid instruction",
            "components/Footer.astro": "",   # пустая инструкция
        })
        result = agent._parse_plan(raw, FILES)
        assert "components/Footer.astro" not in result
        assert "components/Header.astro" in result

    def test_markdown_json_block_is_parsed(self):
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent.__new__(PlannerAgent)
        raw = '```json\n{"components/Header.astro": "blue header"}\n```'
        result = agent._parse_plan(raw, FILES)
        assert result == {"components/Header.astro": "blue header"}

    def test_empty_files_list_returns_empty(self):
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent.__new__(PlannerAgent)
        raw = json.dumps({"components/Header.astro": "change it"})
        result = agent._parse_plan(raw, [])
        assert result == {}


# ---------------------------------------------------------------------------
# plan()
# ---------------------------------------------------------------------------

class TestPlan:

    @pytest.mark.asyncio
    async def test_returns_correct_plan(self):
        llm_out = json.dumps({
            "components/Header.astro": "Сделай заголовок синим",
            "components/Footer.astro": "Добавь copyright",
        })
        agent = _make_planner(llm_out)
        result = await agent.plan("измени хедер и футер", FILES)
        assert "components/Header.astro" in result
        assert "components/Footer.astro" in result

    @pytest.mark.asyncio
    async def test_calls_llm_once(self):
        agent = _make_planner(json.dumps({"pages/index.astro": "change title"}))
        await agent.plan("prompt", FILES)
        agent._call_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_prompt_included_in_llm_call(self):
        agent = _make_planner(json.dumps({}))
        await agent.plan("сделай кнопку красной", FILES)
        _, user_prompt = agent._call_llm.call_args[0]
        assert "сделай кнопку красной" in user_prompt

    @pytest.mark.asyncio
    async def test_files_included_in_llm_call(self):
        agent = _make_planner(json.dumps({}))
        await agent.plan("prompt", FILES)
        _, user_prompt = agent._call_llm.call_args[0]
        for f in FILES:
            assert f in user_prompt

    @pytest.mark.asyncio
    async def test_project_context_included_when_provided(self):
        agent = _make_planner(json.dumps({}))
        await agent.plan("prompt", FILES, project_context="e-commerce сайт")
        _, user_prompt = agent._call_llm.call_args[0]
        assert "e-commerce" in user_prompt

    @pytest.mark.asyncio
    async def test_project_context_absent_when_empty(self):
        agent = _make_planner(json.dumps({}))
        await agent.plan("prompt", FILES, project_context="")
        _, user_prompt = agent._call_llm.call_args[0]
        assert "Контекст" not in user_prompt

    @pytest.mark.asyncio
    async def test_empty_files_list_returns_empty_without_llm_call(self):
        agent = _make_planner(json.dumps({"x.astro": "y"}))
        result = await agent.plan("prompt", [])
        assert result == {}
        agent._call_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_parse_failure_returns_empty(self):
        agent = _make_planner("not json")
        result = await agent.plan("prompt", FILES)
        assert result == {}

    @pytest.mark.asyncio
    async def test_only_valid_files_in_result(self):
        llm_out = json.dumps({
            "components/Header.astro": "ok",
            "FAKE/does_not_exist.astro": "nope",
        })
        agent = _make_planner(llm_out)
        result = await agent.plan("prompt", FILES)
        assert "FAKE/does_not_exist.astro" not in result


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

class TestRun:

    @pytest.mark.asyncio
    async def test_run_returns_plan_key(self):
        llm_out = json.dumps({"components/Header.astro": "change"})
        agent = _make_planner(llm_out)
        result = await agent.run({"prompt": "test", "files": FILES})
        assert "plan" in result

    @pytest.mark.asyncio
    async def test_run_delegates_to_plan(self):
        agent = _make_planner(json.dumps({"pages/index.astro": "smth"}))
        result = await agent.run({
            "prompt": "test prompt",
            "files": FILES,
            "project_context": "blog",
        })
        assert isinstance(result["plan"], dict)
