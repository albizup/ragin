"""@agent decorator — registers an AI agent for one or more models."""
from __future__ import annotations

from typing import Any, Callable

from ragin.agent.prompt import generate_system_prompt
from ragin.agent.runner import AgentRunner
from ragin.agent.tools import ToolDefinition, build_crud_tools
from ragin.core.registry import RouteDefinition, registry
from ragin.core.responses import InternalResponse
from ragin.providers.base import BaseProvider


def agent(
    _cls: type | None = None,
    *,
    model: type | list[type] | None = None,
    provider: BaseProvider | None = None,
    description: str = "",
    tools: list[str] | None = None,
    history_backend: str | None = None,  # reserved for future use
):
    """
    Class decorator that wires an AI agent to registered @resource models.

    Supports multiple usage patterns:

        # Stack directly on @resource (model is the decorated class):
        @agent
        @resource(operations=["crud"])
        class User(Model): ...

        # Stack with explicit config:
        @agent(provider=OpenAIProvider(model="gpt-4o"), description="Manages users.")
        @resource(operations=["crud"])
        class User(Model): ...

        # Separate agent class (legacy):
        @agent(model=User, provider=OpenAIProvider(model="gpt-4o"))
        class UserAgent: ...
    """

    def decorator(cls: type) -> type:
        # Determine models
        if model is not None:
            models = [model] if not isinstance(model, list) else model
        elif hasattr(cls, "_ragin_resource_name"):
            models = [cls]
        else:
            raise ValueError(
                "@agent: no model specified and class is not a @resource. "
                "Either stack @agent on a @resource class or pass model=..."
            )

        tool_defs = _resolve_tools(models, tools or ["crud"])
        system_prompt = generate_system_prompt(models, description)

        runner = AgentRunner(
            provider=provider,
            system_prompt=system_prompt,
            tools=tool_defs,
        )

        # Register POST /<resource>/agent for each model
        for m in models:
            resource_name = getattr(m, "_ragin_resource_name", m.ragin_endpoint_name())
            base_path = getattr(m, "_ragin_base_path", f"/{resource_name}")
            path = f"{base_path}/agent"

            def _make_handler(_runner: AgentRunner = runner) -> Callable:
                def handler(request: Any) -> InternalResponse:
                    body = request.json_body
                    message = body.get("message", "")
                    thread_id = body.get("thread_id")
                    result = _runner.run(message, thread_id=thread_id)
                    return InternalResponse.ok(result)
                handler.__name__ = f"agent_{resource_name}"
                return handler

            registry.register_route(RouteDefinition(
                method="POST",
                path=path,
                handler=_make_handler(),
                model=m,
                operation="agent",
            ))

        # Register tools in global registry so MCP sees the same catalogue
        registry.register_tools(tool_defs)

        # Expose runner on the class for custom tool registration
        cls._ragin_runner = runner  # type: ignore[attr-defined]

        @classmethod  # type: ignore[misc]
        def tool_decorator(klass: type, fn: Callable) -> Callable:  # noqa: N805
            """Register a custom tool: @UserAgent.tool or @User.tool"""
            td = runner.register_custom_tool(fn)
            registry.register_tools([td])
            return fn

        cls.tool = tool_decorator  # type: ignore[attr-defined]

        return cls

    # Support bare @agent (without parentheses)
    if _cls is not None:
        return decorator(_cls)
    return decorator


def _resolve_tools(
    models: list[type],
    tools_config: list[str],
) -> list[ToolDefinition]:
    all_tools: list[ToolDefinition] = []
    for m in models:
        if "crud" in tools_config:
            all_tools.extend(build_crud_tools(m))
        else:
            all_tools.extend(build_crud_tools(m, operations=tools_config))
    return all_tools
