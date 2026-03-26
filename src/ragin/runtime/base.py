from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ragin.core.requests import InternalRequest
    from ragin.core.responses import InternalResponse


class BaseRuntimeProvider(ABC):
    """
    Abstracts the cloud-specific event/response format.
    Implement one provider per cloud target (AWS, GCP, Azure).
    The rest of the framework is completely unaware of the cloud.
    """

    @abstractmethod
    def parse_request(self, event: Any, context: Any) -> InternalRequest:
        """Convert the cloud-native event into an InternalRequest."""
        ...

    @abstractmethod
    def format_response(self, response: InternalResponse) -> Any:
        """Convert an InternalResponse into the cloud-native response format."""
        ...

    def get_handler(self, app: Any):
        """
        Returns a callable entry point ready for the target cloud provider.
        Used by `ragin build` to generate the entry file.
        """
        provider = self

        def handler(event: Any, context: Any = None) -> Any:
            return app.handle(event, context, provider=provider)

        return handler
