from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class RouteDefinition:
    method: str               # "GET", "POST", "PATCH", "PUT", "DELETE"
    path: str                 # "/users/{id}"
    handler: Callable
    model: type | None = None
    operation: str | None = None  # "create" | "list" | "retrieve" | "update" | "delete"


class ResourceRegistry:
    """
    Singleton-style global registry.
    All @resource decorators and app.get/post/... register routes here.
    """

    def __init__(self) -> None:
        self._routes: list[RouteDefinition] = []
        self._models: dict[str, type] = {}

    def register_model(self, name: str, model_cls: type) -> None:
        self._models[name] = model_cls

    def register_route(self, route: RouteDefinition) -> None:
        self._routes.append(route)

    def get_routes(self) -> list[RouteDefinition]:
        return list(self._routes)

    def get_models(self) -> dict[str, type]:
        return dict(self._models)

    def reset(self) -> None:
        """Clears all state — useful in tests."""
        self._routes.clear()
        self._models.clear()


# Module-level singleton used across the whole framework.
registry = ResourceRegistry()
