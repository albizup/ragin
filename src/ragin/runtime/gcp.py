from __future__ import annotations

import json

from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse
from ragin.runtime.base import BaseRuntimeProvider


class GCPProvider(BaseRuntimeProvider):
    """
    Supports Google Cloud Functions (1st and 2nd gen) with HTTP triggers.
    The `event` is a Flask-compatible request object (flask.wrappers.Request).
    """

    def parse_request(self, event, context=None) -> InternalRequest:
        # event is a flask.Request
        return InternalRequest(
            method=event.method,
            path=event.path,
            path_params={},
            query_params=dict(event.args),
            headers=dict(event.headers),
            raw_body=event.get_data(as_text=True) or None,
        )

    def format_response(self, response: InternalResponse):
        # GCF accepts (body, status_code, headers) tuple
        body = json.dumps(response.body, default=str) if response.body is not None else ""
        headers = {"Content-Type": "application/json", **(response.headers or {})}
        return body, response.status_code, headers
