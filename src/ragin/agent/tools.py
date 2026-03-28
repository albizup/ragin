"""Tool binding: generates tool definitions from CRUD operations on models."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ragin.core.fields import get_ragin_meta


@dataclass
class ToolDefinition:
    """Describes a tool that can be invoked by the agent or exposed via MCP."""

    name: str
    description: str
    parameters: dict[str, Any]       # JSON Schema
    handler: Callable[[dict], Any]   # fn(arguments) → result
    model: type | None = None


_PY_TO_JSON: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "UUID": "string",
}


def build_crud_tools(
    model_cls: type,
    operations: list[str] | None = None,
) -> list[ToolDefinition]:
    """
    Generate ToolDefinition objects for the CRUD operations of a model.
    If operations is None all five are generated.
    """
    ops = operations or ["create", "list", "retrieve", "update", "delete"]
    resource_name = getattr(model_cls, "_ragin_resource_name", None) or model_cls.ragin_endpoint_name()
    singular = model_cls.__name__.lower()
    pk_field = model_cls.primary_key_field()
    tools: list[ToolDefinition] = []

    # Build property schemas from model fields
    props: dict[str, dict] = {}
    required: list[str] = []
    for name, fi in model_cls.model_fields.items():
        props[name] = _field_json_schema(fi)
        if fi.is_required():
            required.append(name)

    if "create" in ops:
        tools.append(ToolDefinition(
            name=f"create_{singular}",
            description=f"Create a new {singular}.",
            parameters={
                "type": "object",
                "properties": dict(props),
                "required": list(required),
            },
            handler=_make_crud_caller("POST", f"/{resource_name}", pk_field),
            model=model_cls,
        ))

    if "list" in ops:
        filter_props = {k: v for k, v in props.items()
                        if not get_ragin_meta(model_cls, k).get("primary_key")}
        filter_props["limit"] = {"type": "integer", "description": "Max results", "default": 100}
        filter_props["offset"] = {"type": "integer", "description": "Skip N results", "default": 0}
        tools.append(ToolDefinition(
            name=f"list_{resource_name}",
            description=f"List {resource_name}. Supports filter parameters.",
            parameters={"type": "object", "properties": filter_props},
            handler=_make_crud_caller("GET", f"/{resource_name}", pk_field),
            model=model_cls,
        ))

    if "retrieve" in ops:
        tools.append(ToolDefinition(
            name=f"get_{singular}",
            description=f"Retrieve a single {singular} by {pk_field}.",
            parameters={
                "type": "object",
                "properties": {pk_field: {"type": "string"}},
                "required": [pk_field],
            },
            handler=_make_crud_caller("GET", f"/{resource_name}/{{{pk_field}}}", pk_field),
            model=model_cls,
        ))

    if "update" in ops:
        update_props = {pk_field: {"type": "string"}}
        update_props.update({k: v for k, v in props.items() if k != pk_field})
        tools.append(ToolDefinition(
            name=f"update_{singular}",
            description=f"Update an existing {singular}. Pass only the fields to change plus {pk_field}.",
            parameters={
                "type": "object",
                "properties": update_props,
                "required": [pk_field],
            },
            handler=_make_crud_caller("PATCH", f"/{resource_name}/{{{pk_field}}}", pk_field),
            model=model_cls,
        ))

    if "delete" in ops:
        tools.append(ToolDefinition(
            name=f"delete_{singular}",
            description=f"Delete a {singular} by {pk_field}.",
            parameters={
                "type": "object",
                "properties": {pk_field: {"type": "string"}},
                "required": [pk_field],
            },
            handler=_make_crud_caller("DELETE", f"/{resource_name}/{{{pk_field}}}", pk_field),
            model=model_cls,
        ))

    return tools


def _field_json_schema(field_info: Any) -> dict:
    """Derive a simple JSON Schema entry from a pydantic FieldInfo."""
    ann = field_info.annotation
    type_name = getattr(ann, "__name__", str(ann))
    # Handle Optional[X]
    if hasattr(ann, "__args__"):
        inner = [a for a in ann.__args__ if a is not type(None)]
        if inner:
            type_name = getattr(inner[0], "__name__", str(inner[0]))
    schema: dict[str, Any] = {"type": _PY_TO_JSON.get(type_name, "string")}
    if field_info.description:
        schema["description"] = field_info.description
    return schema


def _make_crud_caller(method: str, path_template: str, pk_field: str = "id") -> Callable[[dict], Any]:
    """
    Create a tool handler that builds an InternalRequest and dispatches it
    through the router — the tool calls the same internal CRUD handlers.
    """

    def handler(arguments: dict) -> Any:
        from ragin.core.registry import registry
        from ragin.core.requests import InternalRequest
        from ragin.core.routing import Router

        pk_value = arguments.get(pk_field)
        path = path_template
        pk_placeholder = f"{{{pk_field}}}"
        if pk_placeholder in path and pk_value is not None:
            path = path.replace(pk_placeholder, str(pk_value))

        if method == "GET":
            query = {k: str(v) for k, v in arguments.items() if k != pk_field}
            body = None
        elif method == "DELETE":
            query = {}
            body = None
        elif method == "POST":
            query = {}
            body = dict(arguments)
        else:
            # PATCH / PUT — pk goes into path, not body
            query = {}
            body = {k: v for k, v in arguments.items() if k != pk_field}

        request = InternalRequest(
            method=method,
            path=path,
            query_params=query,
            raw_body=json.dumps(body) if body else None,
        )

        router = Router(registry.get_routes())
        match = router.match(request)
        if match is None:
            return {"error": f"No route matches {method} {path}"}

        request.path_params = match.path_params
        response = match.route.handler(request)
        return response.body

    return handler
