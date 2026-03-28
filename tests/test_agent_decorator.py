"""Tests for @agent decorator — endpoint registration and dispatch."""
import json

from ragin import Field, Model, ServerlessApp, agent, resource
from ragin.core.requests import InternalRequest
from ragin.providers.base import AgentResponse, BaseProvider, ToolCall


class MockProvider(BaseProvider):
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0

    def complete(self, messages, tools=None):
        resp = self._responses[self._idx]
        self._idx += 1
        return resp


def _make_request(path: str, body: dict) -> InternalRequest:
    return InternalRequest(
        method="POST",
        path=path,
        raw_body=json.dumps(body),
    )


class TestAgentDecorator:
    def test_agent_registers_endpoint(self):
        @resource(operations=["crud"])
        class User(Model):
            id: str = Field(primary_key=True)
            name: str

        mock = MockProvider([AgentResponse(content="Hello!")])

        @agent(model=User, provider=mock, description="Test")
        class UserAgent:
            pass

        app = ServerlessApp()
        req = _make_request("/users/agent", {"message": "hi"})
        result = app.handle(req)
        assert result["statusCode"] == 200
        assert result["body"]["message"] == "Hello!"

    def test_agent_with_tool_call(self):
        @resource(operations=["crud"])
        class Item(Model):
            id: str = Field(primary_key=True)
            title: str

        mock = MockProvider([
            AgentResponse(tool_calls=[
                ToolCall(id="tc1", name="create_item", arguments={
                    "id": "i1", "title": "Widget",
                }),
            ]),
            AgentResponse(content="Created Widget."),
        ])

        @agent(model=Item, provider=mock)
        class ItemAgent:
            pass

        app = ServerlessApp()
        req = _make_request("/items/agent", {"message": "create widget"})
        result = app.handle(req)
        assert result["statusCode"] == 200
        assert "Widget" in result["body"]["message"]

    def test_agent_custom_tool(self):
        @resource(operations=["crud"])
        class Task(Model):
            id: str = Field(primary_key=True)
            title: str

        mock = MockProvider([
            AgentResponse(tool_calls=[
                ToolCall(id="tc2", name="ping", arguments={}),
            ]),
            AgentResponse(content="pong received"),
        ])

        @agent(model=Task, provider=mock)
        class TaskAgent:
            pass

        @TaskAgent.tool
        def ping():
            """Ping test."""
            return "pong"

        app = ServerlessApp()
        req = _make_request("/tasks/agent", {"message": "ping"})
        result = app.handle(req)
        assert result["body"]["tool_calls"][0]["result"] == "pong"

    def test_agent_thread_id(self):
        @resource(operations=["crud"])
        class Note(Model):
            id: str = Field(primary_key=True)
            text: str

        mock = MockProvider([AgentResponse(content="ok")])

        @agent(model=Note, provider=mock)
        class NoteAgent:
            pass

        app = ServerlessApp()
        req = _make_request("/notes/agent", {"message": "hi", "thread_id": "abc"})
        result = app.handle(req)
        assert result["body"]["thread_id"] == "abc"

    def test_bare_agent_on_resource(self):
        """@agent stacked directly on @resource (no separate Agent class)."""
        mock = MockProvider([AgentResponse(content="I'm the bare agent!")])

        @agent(provider=mock)
        @resource(operations=["crud"])
        class Widget(Model):
            id: str = Field(primary_key=True)
            color: str

        app = ServerlessApp()
        req = _make_request("/widgets/agent", {"message": "hi"})
        result = app.handle(req)
        assert result["statusCode"] == 200
        assert result["body"]["message"] == "I'm the bare agent!"

    def test_agent_custom_resource_name(self):
        """@agent uses the canonical resource name from @resource(name=...)."""
        mock = MockProvider([AgentResponse(content="ok")])

        @agent(provider=mock)
        @resource(name="people", operations=["crud"])
        class Person(Model):
            id: str = Field(primary_key=True)
            full_name: str

        app = ServerlessApp()
        req = _make_request("/people/agent", {"message": "hi"})
        result = app.handle(req)
        assert result["statusCode"] == 200

    def test_agent_with_path_prefix(self):
        """@agent uses the canonical path from @resource(path_prefix=...)."""
        mock = MockProvider([AgentResponse(content="ok")])

        @agent(provider=mock)
        @resource(path_prefix="/v1", operations=["crud"])
        class Gizmo(Model):
            id: str = Field(primary_key=True)
            label: str

        app = ServerlessApp()
        req = _make_request("/v1/gizmos/agent", {"message": "hi"})
        result = app.handle(req)
        assert result["statusCode"] == 200
