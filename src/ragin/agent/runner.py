"""Agent runner — stateless LLM + tool-call loop."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ragin.agent.tools import ToolDefinition
from ragin.providers.base import AgentResponse, BaseProvider, ToolCall


MAX_ITERATIONS = 10


class AgentRunner:
    """
    Stateless agent loop.

    For each run():
      1. Build messages (system + user)
      2. Call the LLM with available tools
      3. If tool_calls → execute tools, append results, repeat
      4. If final answer → return AgentResult dict
    """

    def __init__(
        self,
        provider: BaseProvider,
        system_prompt: str,
        tools: list[ToolDefinition],
    ) -> None:
        self.provider = provider
        self.system_prompt = system_prompt
        self._tools: dict[str, ToolDefinition] = {t.name: t for t in tools}
        self._tool_schemas: list[dict] = [_to_schema(t) for t in tools]

    def register_custom_tool(self, fn: Callable) -> None:
        """Register a user-defined tool function on this runner."""
        sig = inspect.signature(fn)
        params: dict[str, dict] = {}
        required: list[str] = []
        for pname, p in sig.parameters.items():
            params[pname] = {"type": "string"}
            if p.default is inspect.Parameter.empty:
                required.append(pname)

        td = ToolDefinition(
            name=fn.__name__,
            description=fn.__doc__ or "",
            parameters={"type": "object", "properties": params, "required": required},
            handler=lambda args, _fn=fn: _fn(**args),
        )
        self._tools[td.name] = td
        self._tool_schemas.append(_to_schema(td))

    def run(self, user_message: str, *, thread_id: str | None = None) -> dict[str, Any]:
        """Execute the agent loop. Returns a dict with message, tool_calls, thread_id."""
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        all_tool_calls: list[dict] = []

        for _ in range(MAX_ITERATIONS):
            response: AgentResponse = self.provider.complete(
                messages=messages,
                tools=self._tool_schemas if self._tool_schemas else None,
            )

            if not response.tool_calls:
                return {
                    "message": response.content or "",
                    "tool_calls": all_tool_calls,
                    "thread_id": thread_id,
                }

            # Execute each tool call
            for tc in response.tool_calls:
                tool = self._tools.get(tc.name)
                if tool is None:
                    result: Any = {"error": f"Unknown tool: {tc.name}"}
                else:
                    try:
                        result = tool.handler(tc.arguments)
                    except Exception as exc:
                        result = {"error": str(exc)}

                all_tool_calls.append({
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "result": result,
                })

                # Feed the result back to the LLM
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tc.to_dict()],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str) if not isinstance(result, str) else result,
                })

        return {
            "message": "Agent reached maximum iterations without a final response.",
            "tool_calls": all_tool_calls,
            "thread_id": thread_id,
        }


def _to_schema(tool: ToolDefinition) -> dict:
    """Convert ToolDefinition to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }
