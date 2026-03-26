from __future__ import annotations

from typing import Any

import pydantic


def Field(
    default: Any = ...,
    *,
    primary_key: bool = False,
    nullable: bool = True,
    unique: bool = False,
    index: bool = False,
    description: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Drop-in replacement for pydantic.Field that carries ragin-specific metadata.
    Metadata is stored in json_schema_extra so Pydantic handles all validation
    unchanged; ragin reads it back via get_ragin_meta().
    """
    ragin_meta: dict[str, Any] = {
        "primary_key": primary_key,
        "nullable": nullable,
        "unique": unique,
        "index": index,
    }

    existing_extra = kwargs.pop("json_schema_extra", {}) or {}
    merged_extra = {**existing_extra, "ragin": ragin_meta}

    return pydantic.Field(
        default,
        description=description,
        json_schema_extra=merged_extra,
        **kwargs,
    )


def get_ragin_meta(model_cls: type, field_name: str) -> dict[str, Any]:
    """Returns the ragin metadata dict for a given field, or {} if absent."""
    field_info = model_cls.model_fields.get(field_name)
    if field_info is None:
        return {}
    extra = field_info.json_schema_extra or {}
    return extra.get("ragin", {})
