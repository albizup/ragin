"""MCP server — JSON-RPC handler implementing Model Context Protocol."""
from __future__ import annotations

import json
from typing import Any

from ragin.agent.tools import ToolDefinition
from ragin.mcp.tools import build_mcp_tool_list


class MCPServer:
    """
    Handles MCP JSON-RPC requests over Streamable HTTP.

    Supported methods:
      - initialize
      - tools/list
      - tools/call
    """

    def __init__(self, tools: list[ToolDefinition]) -> None:
        self._tools: dict[str, ToolDefinition] = {t.name: t for t in tools}
        self._tool_list = tools

    def handle(self, request_body: dict) -> dict:
        """Process a single JSON-RPC request and return the response."""
        method = request_body.get("method")
        params = request_body.get("params", {})
        req_id = request_body.get("id")

        if method == "initialize":
            return _jsonrpc_ok(req_id, {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ragin-mcp", "version": "0.1.0"},
            })

        if method == "tools/list":
            return _jsonrpc_ok(req_id, {
                "tools": build_mcp_tool_list(self._tool_list),
            })

        if method == "tools/call":
            return self._handle_tool_call(req_id, params)

        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    def _handle_tool_call(self, req_id: Any, params: dict) -> dict:
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        tool = self._tools.get(tool_name)  # type: ignore[arg-type]

        if tool is None:
            return _jsonrpc_error(req_id, -32602, f"Unknown tool: {tool_name}")

        try:
            result = tool.handler(arguments)
            return _jsonrpc_ok(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, default=str)}],
            })
        except Exception as exc:
            return _jsonrpc_ok(req_id, {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            })


def _jsonrpc_ok(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
