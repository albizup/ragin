from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InternalResponse:
    """
    Cloud-agnostic HTTP response representation.
    Runtime providers convert this to their native response format.
    """

    status_code: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)

    # --- factories ---

    @classmethod
    def ok(cls, body: Any) -> InternalResponse:
        return cls(status_code=200, body=body)

    @classmethod
    def created(cls, body: Any) -> InternalResponse:
        return cls(status_code=201, body=body)

    @classmethod
    def no_content(cls) -> InternalResponse:
        return cls(status_code=204)

    @classmethod
    def bad_request(cls, message: Any) -> InternalResponse:
        return cls(status_code=400, body={"error": message})

    @classmethod
    def not_found(cls, message: str = "Not found") -> InternalResponse:
        return cls(status_code=404, body={"error": message})

    @classmethod
    def conflict(cls, message: str = "Conflict") -> InternalResponse:
        return cls(status_code=409, body={"error": message})

    @classmethod
    def internal_error(cls, message: str = "Internal server error") -> InternalResponse:
        return cls(status_code=500, body={"error": message})
