"""Tests for agent/tools.py — build_crud_tools and tool execution."""
import pytest

from ragin import Field, Model, resource
from ragin.agent.tools import build_crud_tools


def _make_model():
    """Define model inside function so @resource runs after registry.reset()."""

    @resource(operations=["crud"])
    class ToolUser(Model):
        id: str = Field(primary_key=True)
        name: str
        email: str = Field(description="User email address")

    return ToolUser


class TestBuildCrudTools:
    def test_generates_five_tools(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        names = {t.name for t in tools}
        assert names == {"create_tooluser", "list_toolusers", "get_tooluser",
                         "update_tooluser", "delete_tooluser"}

    def test_selective_operations(self):
        cls = _make_model()
        tools = build_crud_tools(cls, operations=["create", "list"])
        names = {t.name for t in tools}
        assert names == {"create_tooluser", "list_toolusers"}

    def test_create_tool_has_required_fields(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        create = next(t for t in tools if t.name == "create_tooluser")
        assert "id" in create.parameters["required"]
        assert "name" in create.parameters["required"]

    def test_list_tool_has_filter_params(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        list_tool = next(t for t in tools if t.name == "list_toolusers")
        props = list_tool.parameters["properties"]
        assert "limit" in props
        assert "offset" in props
        assert "name" in props

    def test_field_description_propagated(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        create = next(t for t in tools if t.name == "create_tooluser")
        email_prop = create.parameters["properties"]["email"]
        assert email_prop.get("description") == "User email address"

    def test_create_tool_calls_crud(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        create = next(t for t in tools if t.name == "create_tooluser")
        result = create.handler({"id": "t1", "name": "Alice", "email": "a@a.com"})
        assert result["id"] == "t1"
        assert result["name"] == "Alice"

    def test_list_tool_calls_crud(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        create = next(t for t in tools if t.name == "create_tooluser")
        create.handler({"id": "t2", "name": "Bob", "email": "b@b.com"})

        list_tool = next(t for t in tools if t.name == "list_toolusers")
        result = list_tool.handler({})
        assert isinstance(result, list)
        assert any(r["name"] == "Bob" for r in result)

    def test_retrieve_tool_calls_crud(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        create = next(t for t in tools if t.name == "create_tooluser")
        create.handler({"id": "t3", "name": "Carol", "email": "c@c.com"})

        get_tool = next(t for t in tools if t.name == "get_tooluser")
        result = get_tool.handler({"id": "t3"})
        assert result["name"] == "Carol"

    def test_update_tool_calls_crud(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        create = next(t for t in tools if t.name == "create_tooluser")
        create.handler({"id": "t4", "name": "Dave", "email": "d@d.com"})

        update = next(t for t in tools if t.name == "update_tooluser")
        result = update.handler({"id": "t4", "name": "David"})
        assert result["name"] == "David"

    def test_delete_tool_calls_crud(self):
        cls = _make_model()
        tools = build_crud_tools(cls)
        create = next(t for t in tools if t.name == "create_tooluser")
        create.handler({"id": "t5", "name": "Eve", "email": "e@e.com"})

        delete = next(t for t in tools if t.name == "delete_tooluser")
        result = delete.handler({"id": "t5"})
        # delete returns None (204 no-content body)
        assert result is None
