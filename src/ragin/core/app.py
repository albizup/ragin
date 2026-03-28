from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from ragin.core.registry import RouteDefinition, registry
from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse
from ragin.core.routing import Router
from ragin.runtime.base import BaseRuntimeProvider

logger = logging.getLogger("ragin")


class ServerlessApp:
    """
    Central application object. Cloud-agnostic by design.

    Usage:
        app = ServerlessApp()                        # provider from env
        app = ServerlessApp(provider=AWSProvider())  # explicit provider

    Entry point:
        handler = app.get_handler()   # callable for the target cloud
    """

    def __init__(self, provider: BaseRuntimeProvider | None = None) -> None:
        self._provider = provider

    # ------------------------------------------------------------------
    # Provider resolution
    # ------------------------------------------------------------------

    def _resolve_provider(self, override: BaseRuntimeProvider | None) -> BaseRuntimeProvider:
        if override is not None:
            return override
        if self._provider is not None:
            return self._provider
        from ragin.runtime import get_default_provider
        return get_default_provider()

    # ------------------------------------------------------------------
    # Route decorators for global custom endpoints
    # ------------------------------------------------------------------

    def _route_decorator(self, method: str, path: str):
        def decorator(fn):
            registry.register_route(RouteDefinition(method=method, path=path, handler=fn))
            return fn
        return decorator

    def get(self, path: str):    return self._route_decorator("GET", path)
    def post(self, path: str):   return self._route_decorator("POST", path)
    def patch(self, path: str):  return self._route_decorator("PATCH", path)
    def put(self, path: str):    return self._route_decorator("PUT", path)
    def delete(self, path: str): return self._route_decorator("DELETE", path)

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    def handle(self, event: Any, context: Any = None, *, provider: BaseRuntimeProvider | None = None) -> Any:
        """
        Main dispatch method.
        `event` must be in the format expected by the active provider.
        Returns a response in the format produced by the active provider.
        """
        p = self._resolve_provider(provider)
        request: InternalRequest = p.parse_request(event, context)

        router = Router(registry.get_routes())
        match = router.match(request)

        if match is None:
            return p.format_response(InternalResponse.not_found("Route not found"))

        request.path_params = match.path_params

        try:
            response: InternalResponse = match.route.handler(request)
        except ValidationError as exc:
            response = InternalResponse.bad_request(exc.errors())
        except Exception:
            logger.exception("Unhandled error in %s %s", request.method, request.path)
            response = InternalResponse.internal_error()

        return p.format_response(response)

    # ------------------------------------------------------------------
    # Build helper
    # ------------------------------------------------------------------

    def get_handler(self, provider: BaseRuntimeProvider | None = None):
        """
        Returns a callable entry point wired to the given (or default) provider.
        This is what `ragin build` places in the generated entry file.

            handler = app.get_handler()            # reads RAGIN_PROVIDER env
            handler = app.get_handler(AWSProvider())  # explicit
        """
        return self._resolve_provider(provider).get_handler(self)
