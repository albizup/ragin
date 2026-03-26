"""Tests for agent/runner.py — AgentRunner with mock providers."""
import json

import pytest

from ragin import Field, Model, resource
from ragin.agent.runner import AgentRunner
from ragin.agent.tools import build_crud_tools
from ragin.providers.base import AgentResponse, BaseProvider, ToolCall


class MockProvider(BaseProvider):
    """Provider that returns canned responses in order."""

    def __init__(self, responses: list[AgentResponse]) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.call_log: list[dict] = []

    def complete(self, messages, tools=None):
        self.call_log.append({"messages": messages, "tools": tools})
        resp = self._responses[self._idx]
        self._idx += 1
        return resp


@pytest.fixture()
def runner_model():
    """Define model inside fixture so routes exist after registry.reset()."""

    @resource(operations=["crud"])
    class RunnerUser(Model):
        id: str = Field(primary_key=True)
        name: str
        email: str

    return RunnerUser


def _make_runner(model_cls, responses: list[AgentResponse]) -> tuple[AgentRunner, MockProvider]:
    provider = MockProvider(responses)
    tools = build_crud_tools(model_cls)
    runner = AgentRunner(
        provider=provider,
        system_prompt="Test agent",
        tools=tools,
    )
    return runner, provider


class TestAgentRunner:
    def test_simple_message(self, runner_model):
        runner, _ = _make_runner(runner_model, [
            AgentResponse(content="Hello!"),
        ])
        result = runner.run("hi")
        assert result["message"] == "Hello!"
        assert result["tool_calls"] == []

    def test_thread_id_passthrough(self, runner_model):
        runner, _ = _make_runner(runner_model, [AgentResponse(content="ok")])
        result = runner.run("hi", thread_id="t-123")
        assert result["thread_id"] == "t-123"

    def test_tool_call_then_answer(self, runner_model):
        runner, _ = _make_runner(runner_model, [
            AgentResponse(tool_calls=[
                ToolCall(id="tc1", name="create_runneruser", arguments={
                    "id": "u1", "name": "Alice", "email": "a@a.com",
                }),
            ]),
            AgentResponse(content="Created Alice."),
        ])
        result = runner.run("Create user Alice")
        assert result["message"] == "Created Alice."
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "create_runneruser"
        assert result["tool_calls"][0]["result"]["name"] == "Alice"

    def test_unknown_tool(self, runner_model):
        runner, _ = _make_runner(runner_model, [
            AgentResponse(tool_calls=[
                ToolCall(id="tc2", name="nonexistent", arguments={}),
            ]),
            AgentResponse(content="fallback"),
        ])
        result = runner.run("do something")
        assert result["tool_calls"][0]["result"]["error"] == "Unknown tool: nonexistent"

    def test_max_iterations_breaker(self, runner_model):
        """If the LLM always returns tool_calls, the runner caps at MAX_ITERATIONS."""
        infinite_tc = AgentResponse(tool_calls=[
            ToolCall(id="tcX", name="list_runnerusers", arguments={}),
        ])
        runner, _ = _make_runner(runner_model, [infinite_tc] * 15)
        result = runner.run("loop forever")
        assert "maximum iterations" in result["message"]

    def test_custom_tool_registration(self, runner_model):
        runner, _ = _make_runner(runner_model, [
            AgentResponse(tool_calls=[
                ToolCall(id="tc3", name="greet", arguments={"name": "Bob"}),
            ]),
            AgentResponse(content="Done."),
        ])

        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello, {name}!"

        runner.register_custom_tool(greet)
        result = runner.run("greet Bob")
        assert result["tool_calls"][0]["result"] == "Hello, Bob!"

    def test_provider_receives_tool_schemas(self, runner_model):
        runner, provider = _make_runner(runner_model, [AgentResponse(content="ok")])
        runner.run("anything")
        assert len(provider.call_log) == 1
        tools = provider.call_log[0]["tools"]
        assert tools is not None
        names = {t["function"]["name"] for t in tools}
        assert "create_runneruser" in names
