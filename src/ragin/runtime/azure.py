from __future__ import annotations

import json
from urllib.parse import urlparse

from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse
from ragin.runtime.base import BaseRuntimeProvider


class AzureProvider(BaseRuntimeProvider):
    """
    Supports Azure Functions HTTP trigger (azure.functions.HttpRequest).
    azure-functions package is an optional dependency — only imported at runtime.
    """

    def parse_request(self, event, context=None) -> InternalRequest:
        # event is azure.functions.HttpRequest
        parsed_path = urlparse(event.url).path
        return InternalRequest(
            method=event.method,
            path=parsed_path,
            path_params=dict(event.route_params),
            query_params=dict(event.params),
            headers=dict(event.headers),
            raw_body=event.get_body().decode("utf-8") or None,
        )

    def format_response(self, response: InternalResponse):
        import azure.functions as func  # optional dep, imported lazily

        body = json.dumps(response.body, default=str) if response.body is not None else ""
        return func.HttpResponse(
            body=body,
            status_code=response.status_code,
            headers={"Content-Type": "application/json", **(response.headers or {})},
        )
