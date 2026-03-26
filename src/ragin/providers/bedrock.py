"""AWS Bedrock LLM provider (Converse API)."""
from __future__ import annotations

from typing import Any

from ragin.providers.base import AgentResponse, BaseProvider, ToolCall


class BedrockProvider(BaseProvider):
    """Provider for AWS Bedrock via the Converse API."""

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
        region: str = "us-east-1",
        max_tokens: int = 4096,
    ) -> None:
        self.model_id = model_id
        self.region = region
        self._max_tokens = max_tokens
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> AgentResponse:
        system_blocks: list[dict] = []
        converse_msgs: list[dict] = []

        for m in messages:
            if m["role"] == "system":
                system_blocks.append({"text": m["content"]})
            else:
                converse_msgs.append(self._convert_message(m))

        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": converse_msgs,
            "inferenceConfig": {"maxTokens": self._max_tokens},
        }
        if system_blocks:
            kwargs["system"] = system_blocks
        if tools:
            kwargs["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t["function"]["name"],
                            "description": t["function"].get("description", ""),
                            "inputSchema": {"json": t["function"]["parameters"]},
                        }
                    }
                    for t in tools
                ]
            }

        response = self.client.converse(**kwargs)
        output = response["output"]["message"]

        tool_calls: list[ToolCall] = []
        content_parts: list[str] = []

        for block in output["content"]:
            if "text" in block:
                content_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(ToolCall(
                    id=tu["toolUseId"],
                    name=tu["name"],
                    arguments=tu["input"],
                ))

        content = "\n".join(content_parts) if content_parts else None

        if tool_calls:
            return AgentResponse(content=content, tool_calls=tool_calls)
        return AgentResponse(content=content)

    @staticmethod
    def _convert_message(msg: dict) -> dict:
        """Convert from OpenAI-like format to Bedrock Converse format."""
        if msg["role"] == "tool":
            return {
                "role": "user",
                "content": [{
                    "toolResult": {
                        "toolUseId": msg["tool_call_id"],
                        "content": [{"text": msg["content"]}],
                    }
                }],
            }
        if msg.get("tool_calls"):
            return {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": tc["id"],
                            "name": tc["function"]["name"],
                            "input": tc["function"]["arguments"],
                        }
                    }
                    for tc in msg["tool_calls"]
                ],
            }
        return {
            "role": msg["role"],
            "content": [{"text": msg.get("content") or ""}],
        }
