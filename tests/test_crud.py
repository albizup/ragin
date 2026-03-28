"""Integration tests for CRUD endpoints via ServerlessApp + LocalProvider."""
import json
from uuid import uuid4

import pytest

from ragin import ServerlessApp, Model, Field, resource
from ragin.core.requests import InternalRequest
from ragin.runtime.local import LocalProvider


# ---------------------------------------------------------------------------
# App fixture — re-created per test because conftest resets the registry
# ---------------------------------------------------------------------------

@pytest.fixture()
def user_app():
    @resource(operations=["crud"])
    class User(Model):
        id: str = Field(primary_key=True)
        name: str
        email: str

    app = ServerlessApp(provider=LocalProvider())
    return app, User


def _req(method, path, body=None, query=None):
    return InternalRequest(
        method=method,
        path=path,
        query_params=query or {},
        raw_body=json.dumps(body) if body else None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create(user_app):
    app, _ = user_app
    uid = str(uuid4())
    result = app.handle(_req("POST", "/users", body={"id": uid, "name": "Alice", "email": "alice@example.com"}))
    assert result["statusCode"] == 201
    assert result["body"]["id"] == uid
    assert result["body"]["name"] == "Alice"


def test_list_empty(user_app):
    app, _ = user_app
    result = app.handle(_req("GET", "/users"))
    assert result["statusCode"] == 200
    assert result["body"] == []


def test_list_after_create(user_app):
    app, _ = user_app
    for i in range(3):
        app.handle(_req("POST", "/users", body={"id": str(uuid4()), "name": f"User{i}", "email": f"u{i}@test.com"}))
    result = app.handle(_req("GET", "/users"))
    assert result["statusCode"] == 200
    assert len(result["body"]) == 3


def test_retrieve(user_app):
    app, _ = user_app
    uid = str(uuid4())
    app.handle(_req("POST", "/users", body={"id": uid, "name": "Bob", "email": "bob@test.com"}))
    result = app.handle(_req("GET", f"/users/{uid}"))
    assert result["statusCode"] == 200
    assert result["body"]["name"] == "Bob"


def test_retrieve_not_found(user_app):
    app, _ = user_app
    result = app.handle(_req("GET", "/users/nonexistent"))
    assert result["statusCode"] == 404


def test_update(user_app):
    app, _ = user_app
    uid = str(uuid4())
    app.handle(_req("POST", "/users", body={"id": uid, "name": "Carol", "email": "carol@test.com"}))
    result = app.handle(_req("PATCH", f"/users/{uid}", body={"name": "Carol Updated"}))
    assert result["statusCode"] == 200
    assert result["body"]["name"] == "Carol Updated"


def test_delete(user_app):
    app, _ = user_app
    uid = str(uuid4())
    app.handle(_req("POST", "/users", body={"id": uid, "name": "Delete Me", "email": "bye@test.com"}))
    result = app.handle(_req("DELETE", f"/users/{uid}"))
    assert result["statusCode"] == 204
    # verify it's gone
    result2 = app.handle(_req("GET", f"/users/{uid}"))
    assert result2["statusCode"] == 404


def test_delete_not_found(user_app):
    app, _ = user_app
    result = app.handle(_req("DELETE", "/users/ghost"))
    assert result["statusCode"] == 404


def test_route_not_found(user_app):
    app, _ = user_app
    result = app.handle(_req("GET", "/nonexistent"))
    assert result["statusCode"] == 404


def test_create_validation_error(user_app):
    app, _ = user_app
    # missing required 'name' and 'email'
    result = app.handle(_req("POST", "/users", body={"id": str(uuid4())}))
    assert result["statusCode"] == 400


def test_custom_global_endpoint(user_app):
    app, _ = user_app

    @app.get("/health")
    def health(request):
        return InternalResponse(status_code=200, body={"ok": True})

    from ragin.core.responses import InternalResponse
    result = app.handle(_req("GET", "/health"))
    assert result["statusCode"] == 200
    assert result["body"]["ok"] is True


def test_list_with_limit(user_app):
    app, _ = user_app
    for i in range(5):
        app.handle(_req("POST", "/users", body={"id": str(uuid4()), "name": f"User{i}", "email": f"u{i}@test.com"}))
    result = app.handle(_req("GET", "/users", query={"limit": "2"}))
    assert result["statusCode"] == 200
    assert len(result["body"]) == 2


# ---------------------------------------------------------------------------
# Edge-case tests: non-id PK, custom name/prefix, PATCH validation
# ---------------------------------------------------------------------------

def test_non_id_primary_key():
    """Models with PK != 'id' should work end-to-end."""
    @resource(operations=["crud"])
    class Player(Model):
        player_id: str = Field(primary_key=True)
        nickname: str

    app = ServerlessApp(provider=LocalProvider())
    # Create
    result = app.handle(_req("POST", "/players", body={"player_id": "p1", "nickname": "Ace"}))
    assert result["statusCode"] == 201
    assert result["body"]["player_id"] == "p1"
    # Retrieve
    result = app.handle(_req("GET", "/players/p1"))
    assert result["statusCode"] == 200
    assert result["body"]["nickname"] == "Ace"
    # Update
    result = app.handle(_req("PATCH", "/players/p1", body={"nickname": "Ace2"}))
    assert result["statusCode"] == 200
    assert result["body"]["nickname"] == "Ace2"
    # Delete
    result = app.handle(_req("DELETE", "/players/p1"))
    assert result["statusCode"] == 204


def test_resource_custom_name():
    """@resource(name=...) should override the default endpoint name."""
    @resource(name="people", operations=["crud"])
    class Person(Model):
        id: str = Field(primary_key=True)
        full_name: str

    app = ServerlessApp(provider=LocalProvider())
    result = app.handle(_req("POST", "/people", body={"id": "1", "full_name": "Alice"}))
    assert result["statusCode"] == 201
    # Default path should NOT work
    result = app.handle(_req("GET", "/persons"))
    assert result["statusCode"] == 404


def test_resource_path_prefix():
    """@resource(path_prefix=...) should prefix all paths."""
    @resource(path_prefix="/v1", operations=["crud"])
    class Config(Model):
        id: str = Field(primary_key=True)
        value: str

    app = ServerlessApp(provider=LocalProvider())
    result = app.handle(_req("POST", "/v1/configs", body={"id": "c1", "value": "on"}))
    assert result["statusCode"] == 201
    result = app.handle(_req("GET", "/v1/configs/c1"))
    assert result["statusCode"] == 200


def test_update_with_invalid_payload():
    """PATCH with an invalid field type should return 400, not persist."""
    @resource(operations=["crud"])
    class Gadget(Model):
        id: str = Field(primary_key=True)
        name: str
        count: int

    app = ServerlessApp(provider=LocalProvider())
    app.handle(_req("POST", "/gadgets", body={"id": "g1", "name": "Bolt", "count": 5}))
    # Send invalid type for 'count'
    result = app.handle(_req("PATCH", "/gadgets/g1", body={"count": "not-a-number"}))
    assert result["statusCode"] == 400


def test_endpoint_name_from_meta():
    """Meta.endpoint_name should set the REST path."""
    class SpecialItem(Model):
        id: str = Field(primary_key=True)
        label: str
        class Meta:
            endpoint_name = "special"

    resource(operations=["crud"])(SpecialItem)
    app = ServerlessApp(provider=LocalProvider())
    result = app.handle(_req("POST", "/special", body={"id": "s1", "label": "X"}))
    assert result["statusCode"] == 201
