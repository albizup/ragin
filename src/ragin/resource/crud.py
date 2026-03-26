from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse

if TYPE_CHECKING:
    from ragin.core.models import Model


class CrudHandlerFactory:
    """
    Generates the five standard CRUD handlers for a Model as plain closures.
    Handlers are cloud-agnostic: they receive InternalRequest, return InternalResponse.
    They import the backend lazily so it can be configured after module load.
    """

    def __init__(self, model_cls: type[Model], resource_name: str) -> None:
        self.model_cls = model_cls
        self.resource_name = resource_name

    def create_handler(self) -> Callable:
        model_cls = self.model_cls

        def handler(request: InternalRequest) -> InternalResponse:
            from ragin.persistence import get_backend
            from pydantic import ValidationError
            from sqlalchemy.exc import IntegrityError

            try:
                data = model_cls.model_validate(request.json_body)
            except ValidationError as exc:
                return InternalResponse.bad_request(exc.errors())

            try:
                record = get_backend().insert(model_cls, data.model_dump())
            except IntegrityError:
                return InternalResponse.conflict(
                    f"Resource with that key already exists."
                )
            return InternalResponse.created(record)

        handler.__name__ = f"create_{self.resource_name}"
        return handler

    def list_handler(self) -> Callable:
        model_cls = self.model_cls

        def handler(request: InternalRequest) -> InternalResponse:
            from ragin.persistence import get_backend

            raw = dict(request.query_params)
            try:
                limit = int(raw.pop("limit", 100))
                offset = int(raw.pop("offset", 0))
            except (ValueError, TypeError):
                return InternalResponse.bad_request("limit and offset must be integers")

            records = get_backend().select(model_cls, filters=raw, limit=limit, offset=offset)
            return InternalResponse.ok(records)

        handler.__name__ = f"list_{self.resource_name}"
        return handler

    def retrieve_handler(self) -> Callable:
        model_cls = self.model_cls

        def handler(request: InternalRequest) -> InternalResponse:
            from ragin.persistence import get_backend

            pk = request.path_params.get("id")
            record = get_backend().get(model_cls, pk)
            if record is None:
                return InternalResponse.not_found()
            return InternalResponse.ok(record)

        handler.__name__ = f"retrieve_{self.resource_name}"
        return handler

    def update_handler(self) -> Callable:
        model_cls = self.model_cls

        def handler(request: InternalRequest) -> InternalResponse:
            from ragin.persistence import get_backend

            pk = request.path_params.get("id")
            record = get_backend().update(model_cls, pk, request.json_body)
            if record is None:
                return InternalResponse.not_found()
            return InternalResponse.ok(record)

        handler.__name__ = f"update_{self.resource_name}"
        return handler

    def delete_handler(self) -> Callable:
        model_cls = self.model_cls

        def handler(request: InternalRequest) -> InternalResponse:
            from ragin.persistence import get_backend

            pk = request.path_params.get("id")
            deleted = get_backend().delete(model_cls, pk)
            if not deleted:
                return InternalResponse.not_found()
            return InternalResponse.no_content()

        handler.__name__ = f"delete_{self.resource_name}"
        return handler
