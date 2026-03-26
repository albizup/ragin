"""Tests for MCP server — JSON-RPC handler."""
import json

from ragin.agent.tools import ToolDefinition
from ragin.mcp.server import MCPServer


def _echo_handler(arguments: dict):
    return {"echo": arguments}


def _make_server() -> MCPServer:
    tools = [
        ToolDefinition(
            name="echo",
            description="Echoes input back.",
            parameters={
                "type": "object",
                "properties": {"msg": {"type": "string"}},
                "required": ["msg"],
            },
            handler=_echo_handler,
        ),
    ]
    return MCPServer(tools)


class TestMCPServer:
    def test_initialize(self):
        server = _make_server()
        result = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert result["result"]["protocolVersion"] == "2025-03-26"
        assert result["result"]["serverInfo"]["name"] == "ragin-mcp"

    def test_tools_list(self):
        server = _make_server()
        result = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = result["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "echo"
        assert "inputSchema" in tools[0]

    def test_tools_call(self):
        server = _make_server()
        result = server.handle({
            "jsonrpc": "2.0", "id": 3,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"msg": "hello"}},
        })
        content = result["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        parsed = json.loads(content[0]["text"])
        assert parsed == {"echo": {"msg": "hello"}}

    def test_tools_call_unknown_tool(self):
        server = _make_server()
        result = server.handle({
            "jsonrpc": "2.0", "id": 4,
            "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}},
        })
        assert "error" in result
        assert result["error"]["code"] == -32602

    def test_unknown_method(self):
        server = _make_server()
        result = server.handle({
            "jsonrpc": "2.0", "id": 5,
            "method": "foo/bar",
        })
        assert "error" in result
        assert result["error"]["code"] == -32601

    def test_tools_call_with_error(self):
        def failing_handler(arguments):
            raise ValueError("boom")

        server = MCPServer([
            ToolDefinition(
                name="fail",
                description="Always fails.",
                parameters={"type": "object", "properties": {}},
                handler=failing_handler,
            ),
        ])
        result = server.handle({
            "jsonrpc": "2.0", "id": 6,
            "method": "tools/call",
            "params": {"name": "fail", "arguments": {}},
        })
        assert result["result"]["isError"] is True
        assert "boom" in result["result"]["content"][0]["text"]
