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
