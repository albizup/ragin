"""Tests for the Router — path matching and param extraction."""
from ragin.core.requests import InternalRequest
from ragin.core.routing import Router
from ragin.core.registry import RouteDefinition


def _dummy(req): pass


def _make_router(*specs):
    routes = [RouteDefinition(method=m, path=p, handler=_dummy) for m, p in specs]
    return Router(routes)


def test_static_route():
    router = _make_router(("GET", "/health"))
    req = InternalRequest(method="GET", path="/health")
    match = router.match(req)
    assert match is not None
    assert match.path_params == {}


def test_path_param_extraction():
    router = _make_router(("GET", "/users/{id}"))
    req = InternalRequest(method="GET", path="/users/abc-123")
    match = router.match(req)
    assert match is not None
    assert match.path_params == {"id": "abc-123"}


def test_method_mismatch():
    router = _make_router(("GET", "/users"))
    req = InternalRequest(method="POST", path="/users")
    assert router.match(req) is None


def test_no_match():
    router = _make_router(("GET", "/users"))
    req = InternalRequest(method="GET", path="/unknown")
    assert router.match(req) is None


def test_multiple_routes_correct_match():
    router = _make_router(
        ("GET",    "/users"),
        ("POST",   "/users"),
        ("GET",    "/users/{id}"),
        ("DELETE", "/users/{id}"),
    )
    req = InternalRequest(method="DELETE", path="/users/xyz")
    match = router.match(req)
    assert match is not None
    assert match.path_params == {"id": "xyz"}
    assert match.route.method == "DELETE"
