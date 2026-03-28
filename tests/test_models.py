"""Tests for Field metadata and Model utilities."""
import pytest

from ragin.core.fields import Field, get_ragin_meta
from ragin.core.models import Model


class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str
    role: str = Field(nullable=True, index=True)


def test_field_primary_key_meta():
    meta = get_ragin_meta(User, "id")
    assert meta["primary_key"] is True


def test_field_default_meta():
    meta = get_ragin_meta(User, "name")
    assert meta.get("primary_key") is False or meta.get("primary_key") is None or meta == {}
    # name has no ragin meta → empty dict
    # (plain pydantic field, no json_schema_extra)


def test_field_nullable_index_meta():
    meta = get_ragin_meta(User, "role")
    assert meta["nullable"] is True
    assert meta["index"] is True


def test_primary_key_field():
    assert User.primary_key_field() == "id"


def test_table_name_default():
    assert User.ragin_table_name() == "users"


def test_endpoint_name_default():
    assert User.ragin_endpoint_name() == "users"


def test_endpoint_name_custom():
    class Bar(Model):
        id: str = Field(primary_key=True)
        class Meta:
            endpoint_name = "bar_customs"
    assert Bar.ragin_endpoint_name() == "bar_customs"


def test_table_name_custom():
    class Foo(Model):
        id: str = Field(primary_key=True)
        class Meta:
            table_name = "foo_customs"
    assert Foo.ragin_table_name() == "foo_customs"


def test_model_without_pk_raises():
    class NoPK(Model):
        name: str

    with pytest.raises(ValueError, match="primary_key"):
        NoPK.primary_key_field()
