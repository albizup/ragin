from __future__ import annotations

import json

from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse
from ragin.runtime.base import BaseRuntimeProvider


class AWSProvider(BaseRuntimeProvider):
    """
    Supports AWS Lambda with API Gateway HTTP API (payload format V2).
    https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html
    """

    def parse_request(self, event: dict, context=None) -> InternalRequest:
        http_ctx = event.get("requestContext", {}).get("http", {})
        return InternalRequest(
            method=http_ctx.get("method", "GET"),
            path=http_ctx.get("path", "/"),
            path_params=event.get("pathParameters") or {},
            query_params=event.get("queryStringParameters") or {},
            headers=event.get("headers") or {},
            raw_body=event.get("body"),
        )

    def format_response(self, response: InternalResponse) -> dict:
        body = ""
        if response.body is not None:
            body = json.dumps(response.body, default=str)
        return {
            "statusCode": response.status_code,
            "headers": {
                "Content-Type": "application/json",
                **(response.headers or {}),
            },
            "body": body,
        }
