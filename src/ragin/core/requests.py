from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class InternalRequest:
    """
    Cloud-agnostic HTTP request representation.
    Nothing in here is specific to AWS, GCP or Azure.
    Runtime providers are responsible for producing this from their native event.
    """

    method: str                                    # "GET", "POST", ...
    path: str                                      # "/users/abc-123"
    path_params: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    raw_body: str | None = None

    @property
    def json_body(self) -> dict:
        if not self.raw_body:
            return {}
        return json.loads(self.raw_body)
