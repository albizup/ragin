"""Tests for LLM provider base classes."""
from ragin.providers.base import AgentResponse, BaseProvider, ToolCall


def test_tool_call_to_dict():
    tc = ToolCall(id="tc-1", name="my_tool", arguments={"x": 1})
    d = tc.to_dict()
    assert d["id"] == "tc-1"
    assert d["type"] == "function"
    assert d["function"]["name"] == "my_tool"
    assert d["function"]["arguments"] == {"x": 1}


def test_agent_response_defaults():
    r = AgentResponse()
    assert r.content is None
    assert r.tool_calls == []


def test_agent_response_with_content():
    r = AgentResponse(content="hello")
    assert r.content == "hello"
    assert not r.tool_calls


def test_agent_response_with_tool_calls():
    tc = ToolCall(id="a", name="b", arguments={})
    r = AgentResponse(tool_calls=[tc])
    assert len(r.tool_calls) == 1


def test_base_provider_not_implemented():
    p = BaseProvider()
    try:
        p.complete([])
        assert False, "Should have raised"
    except NotImplementedError:
        pass


def test_lazy_provider_imports():
    """Verify that provider __init__ exports work via __getattr__."""
    import ragin.providers as p
    assert hasattr(p, "OpenAIProvider")
    assert hasattr(p, "AnthropicProvider")
    assert hasattr(p, "BedrockProvider")
