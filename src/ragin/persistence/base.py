from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseBackend(ABC):

    @abstractmethod
    def register(self, model_cls: type) -> None:
        """Register a model and ensure its table/collection exists."""
        ...

    @abstractmethod
    def insert(self, model_cls: type, data: dict) -> dict:
        ...

    @abstractmethod
    def select(self, model_cls: type, filters: dict, limit: int, offset: int) -> list[dict]:
        ...

    @abstractmethod
    def get(self, model_cls: type, pk_value: Any) -> dict | None:
        ...

    @abstractmethod
    def update(self, model_cls: type, pk_value: Any, data: dict) -> dict | None:
        ...

    @abstractmethod
    def delete(self, model_cls: type, pk_value: Any) -> bool:
        ...
