"""Unit-тесты для проверки core-config, core-agent-base, core-agents.

Запуск:
    cd backend
    pip install pytest pytest-asyncio
    pytest tests/test_core_changes.py -v
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest



# Конфигурация (core-config)


class TestConfig:
    def test_redis_url_exists(self):
        from app.core.config import Settings
        fields = Settings.model_fields
        assert "REDIS_URL" in fields, "REDIS_URL must be in Settings"

    def test_redis_url_default(self):
        from app.core.config import Settings
        default = Settings.model_fields["REDIS_URL"].default
        assert default == "redis://localhost:6379/0"

    def test_removed_jwt_fields(self):
        from app.core.config import Settings
        fields = Settings.model_fields
        for removed in ("SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES"):
            assert removed not in fields, f"{removed} should be removed from Settings"

    def test_required_fields_still_present(self):
        from app.core.config import Settings
        fields = Settings.model_fields
        for required in ("DATABASE_URL", "SYNC_DATABASE_URL", "OPENAI_API_KEY",
                         "MINIO_ENDPOINT", "RABBITMQ_URL"):
            assert required in fields, f"{required} must still be in Settings"



# Базовый агент: _extract_json


class TestExtractJson:
    def setup_method(self):
        # конкретный класс нужен чтобы вызвать abstractmethod-класс
        from app.agents.base import BaseAgent

        class _ConcreteAgent(BaseAgent):
            async def run(self, input_data):
                return {}

        self.agent = _ConcreteAgent()

    def test_plain_json(self):
        raw = '{"key": "value", "num": 42}'
        result = self.agent._extract_json(raw)
        assert result == {"key": "value", "num": 42}

    def test_markdown_json_block(self):
        raw = '```json\n{"pages": ["index", "about"]}\n```'
        result = self.agent._extract_json(raw)
        assert result == {"pages": ["index", "about"]}

    def test_markdown_block_without_language(self):
        raw = '```\n{"files": []}\n```'
        result = self.agent._extract_json(raw)
        assert result == {"files": []}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            self.agent._extract_json("not json at all")



# Базовый агент: _call_llm


@pytest.mark.asyncio
class TestCallLlm:
    def _make_agent(self):
        from app.agents.base import BaseAgent

        class _ConcreteAgent(BaseAgent):
            async def run(self, input_data):
                return {}

        return _ConcreteAgent()

    def _mock_response(self, content: str):
        """Строит фейковый ответ chat.completions.create()."""
        choice = MagicMock()
        choice.message.content = content
        response = MagicMock()
        response.choices = [choice]
        return response

    async def test_returns_content(self):
        agent = self._make_agent()
        agent.client = MagicMock()
        agent.client.chat.completions.create = AsyncMock(
            return_value=self._mock_response('{"result": "ok"}')
        )

        result = await agent._call_llm("sys", "user")
        assert result == '{"result": "ok"}'

    async def test_called_with_correct_messages(self):
        agent = self._make_agent()
        agent.client = MagicMock()
        mock_create = AsyncMock(return_value=self._mock_response("response"))
        agent.client.chat.completions.create = mock_create

        await agent._call_llm("system prompt", "user prompt")

        _, kwargs = mock_create.call_args
        messages = kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "system prompt"}
        assert messages[1] == {"role": "user", "content": "user prompt"}

    async def test_raises_on_none_content(self):
        agent = self._make_agent()
        agent.client = MagicMock()
        agent.client.chat.completions.create = AsyncMock(
            return_value=self._mock_response(None)
        )

        with pytest.raises(ValueError, match="empty content"):
            await agent._call_llm("sys", "user")

    async def test_retries_on_exception(self):
        """tenacity должен повторить вызов после исключения."""
        agent = self._make_agent()
        agent.client = MagicMock()

        call_count = 0

        async def _flaky(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("temporary error")
            return self._mock_response("ok after retries")

        agent.client.chat.completions.create = _flaky

        result = await agent._call_llm("sys", "user")
        assert result == "ok after retries"
        assert call_count == 3



# Агент A0: OptimizerAgent.run()


@pytest.mark.asyncio
class TestOptimizerAgent:
    def _make_agent(self, llm_response: str):
        from app.agents.optimizer import OptimizerAgent
        agent = OptimizerAgent()
        agent._call_llm = AsyncMock(return_value=llm_response)
        return agent

    async def test_returns_parsed_json(self):
        payload = {"pages": ["index"], "global_style": {}, "components": []}
        agent = self._make_agent(json.dumps(payload))
        result = await agent.run({"prompt": "Лендинг для кофейни"})
        assert result == payload

    async def test_prompt_in_user_message(self):
        agent = self._make_agent('{"pages": []}')
        await agent.run({"prompt": "my prompt"})
        _, user_prompt = agent._call_llm.call_args[0]
        assert "my prompt" in user_prompt

    async def test_template_slug_appended(self):
        agent = self._make_agent('{"pages": []}')
        await agent.run({"prompt": "test", "template_slug": "landing-v1"})
        _, user_prompt = agent._call_llm.call_args[0]
        assert "landing-v1" in user_prompt

    async def test_no_template_slug(self):
        agent = self._make_agent('{"pages": []}')
        await agent.run({"prompt": "test"})
        _, user_prompt = agent._call_llm.call_args[0]
        assert "шаблон" not in user_prompt.lower() or "None" not in user_prompt



# Агент A1: ArchitectAgent.run()


@pytest.mark.asyncio
class TestArchitectAgent:
    def _make_agent(self, llm_response: str):
        from app.agents.architect import ArchitectAgent
        agent = ArchitectAgent()
        agent._call_llm = AsyncMock(return_value=llm_response)
        return agent

    async def test_returns_parsed_json(self):
        payload = {"files": [{"path": "src/pages/index.astro", "description": "Main page"}]}
        agent = self._make_agent(json.dumps(payload))
        result = await agent.run({"pages": ["index"]})
        assert result == payload

    async def test_input_data_serialized_in_prompt(self):
        agent = self._make_agent('{"files": []}')
        spec = {"pages": ["index"], "components": ["Hero"]}
        await agent.run(spec)
        _, user_prompt = agent._call_llm.call_args[0]
        assert "index" in user_prompt
        assert "Hero" in user_prompt

    async def test_markdown_json_unwrapped(self):
        payload = {"files": []}
        wrapped = f"```json\n{json.dumps(payload)}\n```"
        agent = self._make_agent(wrapped)
        result = await agent.run({})
        assert result == payload



# Агент A2: CodeGeneratorAgent.run()


@pytest.mark.asyncio
class TestCodeGeneratorAgent:
    def _make_agent(self, llm_response: str):
        from app.agents.code_generator import CodeGeneratorAgent
        agent = CodeGeneratorAgent()
        agent._call_llm = AsyncMock(return_value=llm_response)
        return agent

    async def test_returns_path_and_content(self):
        code = "---\n---\n<h1>Hello</h1>"
        agent = self._make_agent(code)
        result = await agent.run({
            "file": {"path": "src/pages/index.astro", "description": "Main page"},
            "project_spec": {},
        })
        assert result["path"] == "src/pages/index.astro"
        assert result["content"] == code

    async def test_file_spec_in_prompt(self):
        agent = self._make_agent("code")
        await agent.run({
            "file": {"path": "src/components/Hero.astro", "description": "Hero section"},
            "project_spec": {"pages": ["index"]},
        })
        _, user_prompt = agent._call_llm.call_args[0]
        assert "Hero.astro" in user_prompt
        assert "Hero section" in user_prompt

    async def test_project_spec_in_prompt(self):
        agent = self._make_agent("code")
        await agent.run({
            "file": {"path": "src/pages/index.astro", "description": "Main"},
            "project_spec": {"global_style": {"primary_color": "#ff0000"}},
        })
        _, user_prompt = agent._call_llm.call_args[0]
        assert "#ff0000" in user_prompt

    async def test_content_is_raw_not_parsed(self):
        """A2 возвращает сырой код, не парсит JSON."""
        raw_code = "const x = 1;\nexport default x;"
        agent = self._make_agent(raw_code)
        result = await agent.run({
            "file": {"path": "src/utils/helper.ts", "description": "Helper"},
        })
        assert result["content"] == raw_code
