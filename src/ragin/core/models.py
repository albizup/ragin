from __future__ import annotations

from pydantic import BaseModel

from ragin.core.fields import get_ragin_meta


class Model(BaseModel):
    """
    Base class for all ragin models.
    Thin wrapper around pydantic.BaseModel — all validation is Pydantic's.
    Adds ragin-specific class-level utilities.
    """

    @classmethod
    def primary_key_field(cls) -> str:
        """Returns the name of the field marked as primary_key=True."""
        for name in cls.model_fields:
            if get_ragin_meta(cls, name).get("primary_key"):
                return name
        raise ValueError(f"{cls.__name__} has no Field(primary_key=True)")

    @classmethod
    def ragin_table_name(cls) -> str:
        """
        Returns the DB table name.
        Overridable via inner Meta class:
            class Meta:
                table_name = "app_users"
        """
        meta = getattr(cls, "Meta", None)
        if meta and hasattr(meta, "table_name"):
            return meta.table_name
        return cls.__name__.lower() + "s"

    model_config = {"from_attributes": True}
