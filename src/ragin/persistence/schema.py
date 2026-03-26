from __future__ import annotations

import datetime
import uuid
from typing import Any

import sqlalchemy as sa

from ragin.core.fields import get_ragin_meta
from ragin.core.models import Model

# Mapping from Python / Pydantic annotation name → SQLAlchemy type
_TYPE_MAP: dict[str, Any] = {
    "str":       sa.String,
    "int":       sa.Integer,
    "float":     sa.Float,
    "bool":      sa.Boolean,
    "UUID":      sa.Uuid,
    "datetime":  sa.DateTime,
    "date":      sa.Date,
    "bytes":     sa.LargeBinary,
}


def model_to_table(model_cls: type[Model], metadata: sa.MetaData) -> sa.Table:
    """
    Derives a SQLAlchemy Core Table from a ragin Model class.
    Never touches the ORM layer — uses only sa.Table and sa.Column.
    """
    columns: list[sa.Column] = []

    for field_name, field_info in model_cls.model_fields.items():
        meta = get_ragin_meta(model_cls, field_name)
        sa_type = _resolve_sa_type(field_info.annotation)

        col = sa.Column(
            field_name,
            sa_type,
            primary_key=meta.get("primary_key", False),
            nullable=meta.get("nullable", True),
            unique=meta.get("unique", False),
            index=meta.get("index", False),
        )
        columns.append(col)

    return sa.Table(model_cls.ragin_table_name(), metadata, *columns)


def _resolve_sa_type(annotation: Any) -> sa.types.TypeEngine:
    """
    Resolves the SQLAlchemy column type from a Python type annotation.
    Handles Optional[X] (Union[X, None]) by unwrapping to X.
    """
    # Unwrap Optional / Union with None
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        args = [a for a in getattr(annotation, "__args__", ()) if a is not type(None)]
        if args:
            annotation = args[0]

    type_name = getattr(annotation, "__name__", None) or str(annotation)

    sa_cls = _TYPE_MAP.get(type_name, sa.String)
    return sa_cls()
