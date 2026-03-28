from __future__ import annotations

from typing import Callable

from ragin.core.registry import RouteDefinition, registry
from ragin.resource.crud import CrudHandlerFactory

_CRUD_SHORTCUT = {"crud"}
_ALL_OPERATIONS = ["create", "list", "retrieve", "update", "delete"]

_OP_METHOD: dict[str, str] = {
    "create":   "POST",
    "list":     "GET",
    "retrieve": "GET",
    "update":   "PATCH",
    "delete":   "DELETE",
}


def resource(
    name: str | None = None,
    operations: list[str] | None = None,
    path_prefix: str = "",
):
    """
    Class decorator that registers a Model as a REST resource.

    Usage:
        @resource(operations=["crud"])
        class User(Model):
            ...

    This generates CRUD routes and registers them in the global registry.
    The class is returned unchanged — it's still a plain Pydantic model.
    """

    def decorator(model_cls):
        resource_name = name or model_cls.ragin_endpoint_name()
        pk_field = model_cls.primary_key_field()
        ops = _parse_operations(operations or ["crud"])
        base_path = f"{path_prefix}/{resource_name}"
        pk_path = f"{base_path}/{{{pk_field}}}"

        factory = CrudHandlerFactory(model_cls, resource_name, pk_field)

        op_handlers: dict[str, Callable] = {
            "create":   factory.create_handler(),
            "list":     factory.list_handler(),
            "retrieve": factory.retrieve_handler(),
            "update":   factory.update_handler(),
            "delete":   factory.delete_handler(),
        }

        registry.register_model(resource_name, model_cls)

        for op in ops:
            method = _OP_METHOD[op]
            path = pk_path if op in ("retrieve", "update", "delete") else base_path
            registry.register_route(RouteDefinition(
                method=method,
                path=path,
                handler=op_handlers[op],
                model=model_cls,
                operation=op,
            ))

        # Attach canonical metadata used by @agent and other layers
        model_cls._ragin_resource_name = resource_name
        model_cls._ragin_base_path = base_path
        model_cls._ragin_pk_field = pk_field

        # Resource-scoped custom endpoints: @User.get("/{id}/profile")
        model_cls.get    = classmethod(lambda cls, p: _resource_route("GET",    cls, p))
        model_cls.post   = classmethod(lambda cls, p: _resource_route("POST",   cls, p))
        model_cls.patch  = classmethod(lambda cls, p: _resource_route("PATCH",  cls, p))
        model_cls.put    = classmethod(lambda cls, p: _resource_route("PUT",    cls, p))
        model_cls.delete = classmethod(lambda cls, p: _resource_route("DELETE", cls, p))

        return model_cls

    return decorator


def _parse_operations(ops: list[str]) -> list[str]:
    if set(ops) == _CRUD_SHORTCUT or ops == ["crud"]:
        return _ALL_OPERATIONS
    invalid = set(ops) - set(_ALL_OPERATIONS)
    if invalid:
        raise ValueError(f"Unknown operations: {invalid}. Valid: {_ALL_OPERATIONS}")
    return ops


def _resource_route(method: str, model_cls: type, sub_path: str) -> Callable:
    """Returns a decorator that registers a resource-scoped custom endpoint."""
    def decorator(fn: Callable) -> Callable:
        full_path = model_cls._ragin_base_path + sub_path
        registry.register_route(RouteDefinition(
            method=method,
            path=full_path,
            handler=fn,
            model=model_cls,
        ))
        return fn
    return decorator
