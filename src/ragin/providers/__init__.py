"""LLM provider package — lazy imports to avoid requiring optional deps."""
from __future__ import annotations

from ragin.providers.base import AgentResponse, BaseProvider, ToolCall

__all__ = ["AgentResponse", "BaseProvider", "ToolCall"]


def __getattr__(name: str):
    if name == "OpenAIProvider":
        from ragin.providers.openai import OpenAIProvider
        return OpenAIProvider
    if name == "AnthropicProvider":
        from ragin.providers.anthropic import AnthropicProvider
        return AnthropicProvider
    if name == "BedrockProvider":
        from ragin.providers.bedrock import BedrockProvider
        return BedrockProvider
    raise AttributeError(f"module 'ragin.providers' has no attribute {name!r}")
