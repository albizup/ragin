"""MCP tool schema generation from ToolDefinition objects."""
from __future__ import annotations

from ragin.agent.tools import ToolDefinition


def tool_to_mcp_schema(tool: ToolDefinition) -> dict:
    """Convert a ToolDefinition to MCP tools/list format."""
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.parameters,
    }


def build_mcp_tool_list(tools: list[ToolDefinition]) -> list[dict]:
    """Build the full list for an MCP tools/list response."""
    return [tool_to_mcp_schema(t) for t in tools]
