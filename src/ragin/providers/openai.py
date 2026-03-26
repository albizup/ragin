"""OpenAI LLM provider."""
from __future__ import annotations

import json
from typing import Any

from ragin.providers.base import AgentResponse, BaseProvider, ToolCall


class OpenAIProvider(BaseProvider):
    """Provider for the OpenAI chat completions API (gpt-4o, gpt-4o-mini, …)."""

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None, **kwargs: Any) -> None:
        self.model = model
        self._api_key = api_key
        self._extra = kwargs
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            import openai

            kw: dict[str, Any] = {}
            if self._api_key:
                kw["api_key"] = self._api_key
            kw.update(self._extra)
            self._client = openai.OpenAI(**kw)
        return self._client

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> AgentResponse:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        if message.tool_calls:
            return AgentResponse(
                content=message.content,
                tool_calls=[
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                    for tc in message.tool_calls
                ],
            )

        return AgentResponse(content=message.content)
