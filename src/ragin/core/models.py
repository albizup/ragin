from __future__ import annotations

from pydantic import BaseModel

from ragin.core.fields import get_ragin_meta

_VOWELS = frozenset("aeiou")


def _pluralize(word: str) -> str:
    """Simple English pluralization for model names."""
    if not word:
        return word
    if word.endswith(("sh", "ch")):
        return word + "es"
    if word.endswith(("s", "x", "z")):
        return word + "es"
    if word.endswith("y") and len(word) > 1 and word[-2] not in _VOWELS:
        return word[:-1] + "ies"
    return word + "s"


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
        Default: smart-pluralized lowercase class name.
        """
        meta = getattr(cls, "Meta", None)
        if meta and hasattr(meta, "table_name"):
            return meta.table_name
        return _pluralize(cls.__name__.lower())

    @classmethod
    def ragin_endpoint_name(cls) -> str:
        """
        Returns the REST endpoint name for this model.
        Overridable via inner Meta class:
            class Meta:
                endpoint_name = "people"
        Default: smart-pluralized lowercase class name.
        """
        meta = getattr(cls, "Meta", None)
        if meta and hasattr(meta, "endpoint_name"):
            return meta.endpoint_name
        return _pluralize(cls.__name__.lower())

    model_config = {"from_attributes": True}
