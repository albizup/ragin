from __future__ import annotations

import json

from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

from ragin.core.requests import InternalRequest
from ragin.runtime.local import LocalProvider


def create_wsgi_app(app):
    provider = LocalProvider()

    def wsgi_app(environ, start_response):
        http_req = Request(environ)
        internal_req = InternalRequest(
            method=http_req.method,
            path=http_req.path,
            path_params={},
            query_params=dict(http_req.args),
            headers=dict(http_req.headers),
            raw_body=http_req.get_data(as_text=True) or None,
        )
        result = app.handle(internal_req, context=None, provider=provider)

        body = result.get("body")
        body_str = json.dumps(body, default=str) if body is not None else ""
        response = Response(
            body_str,
            status=result.get("statusCode", 200),
            headers={"Content-Type": "application/json", **result.get("headers", {})},
        )
        return response(environ, start_response)

    return wsgi_app


def run_dev_server(app, host: str = "127.0.0.1", port: int = 8000) -> None:
    wsgi = create_wsgi_app(app)
    print(f"ragin dev  →  http://{host}:{port}")
    run_simple(host, port, wsgi, use_reloader=True, use_debugger=True)
