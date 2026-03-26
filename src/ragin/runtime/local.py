from __future__ import annotations

from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse
from ragin.runtime.base import BaseRuntimeProvider


class LocalProvider(BaseRuntimeProvider):
    """
    Used in the dev server and in tests.
    parse_request() is the identity function — the caller passes InternalRequest directly.
    format_response() returns a plain dict for easy assertion in tests.
    """

    def parse_request(self, event: InternalRequest, context=None) -> InternalRequest:
        return event

    def format_response(self, response: InternalResponse) -> dict:
        return {
            "statusCode": response.status_code,
            "headers": response.headers or {},
            "body": response.body,
        }
