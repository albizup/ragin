"""Anthropic LLM provider."""
from __future__ import annotations

from typing import Any

from ragin.providers.base import AgentResponse, BaseProvider, ToolCall


class AnthropicProvider(BaseProvider):
    """Provider for the Anthropic Messages API (Claude 3.5, Claude 4, …)."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._extra = kwargs
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            kw: dict[str, Any] = {}
            if self._api_key:
                kw["api_key"] = self._api_key
            kw.update(self._extra)
            self._client = anthropic.Anthropic(**kw)
        return self._client

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> AgentResponse:
        system: str | None = None
        filtered: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            elif m["role"] == "tool":
                # Convert to Anthropic's tool_result format
                filtered.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": m["content"],
                    }],
                })
            elif m.get("tool_calls"):
                # Convert assistant tool_calls to Anthropic content blocks
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": tc["function"]["arguments"],
                    })
                filtered.append({"role": "assistant", "content": blocks})
            else:
                filtered.append(m)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": filtered,
            "max_tokens": self._max_tokens,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ]

        response = self.client.messages.create(**kwargs)

        tool_calls: list[ToolCall] = []
        content_parts: list[str] = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))

        content = "\n".join(content_parts) if content_parts else None

        if tool_calls:
            return AgentResponse(content=content, tool_calls=tool_calls)
        return AgentResponse(content=content)
