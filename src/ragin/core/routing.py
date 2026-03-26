from __future__ import annotations

import re
from dataclasses import dataclass

from ragin.core.registry import RouteDefinition
from ragin.core.requests import InternalRequest


@dataclass
class RouteMatch:
    route: RouteDefinition
    path_params: dict[str, str]


class Router:
    """
    Matches (method, path) pairs against registered RouteDefinitions.
    Supports path parameters in curly-brace syntax: /users/{id}
    More specific routes (fewer params) match before less specific ones
    because they are registered first by convention.
    """

    def __init__(self, routes: list[RouteDefinition]) -> None:
        self._compiled: list[tuple[re.Pattern, RouteDefinition]] = [
            (self._compile(r), r) for r in routes
        ]

    @staticmethod
    def _compile(route: RouteDefinition) -> re.Pattern:
        """Converts /users/{id} → ^/users/(?P<id>[^/]+)$"""
        pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", route.path)
        return re.compile(f"^{pattern}$")

    def match(self, request: InternalRequest) -> RouteMatch | None:
        for pattern, route in self._compiled:
            if route.method != request.method:
                continue
            m = pattern.match(request.path)
            if m:
                return RouteMatch(route=route, path_params=m.groupdict())
        return None
