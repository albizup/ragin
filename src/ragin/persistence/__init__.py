from __future__ import annotations

import os

from ragin.persistence.base import BaseBackend

_backend: BaseBackend | None = None


def configure_backend(url: str) -> None:
    """
    Explicitly configure the SQL backend.
    Call this once at app startup before any request is handled.

        configure_backend(os.environ["DATABASE_URL"])
    """
    global _backend
    from ragin.persistence.sql import SqlBackend
    _backend = SqlBackend(url)


def get_backend() -> BaseBackend:
    """
    Returns the active backend, auto-initialising from RAGIN_DB_URL env var
    if not yet configured. Falls back to a local SQLite file.
    """
    global _backend
    if _backend is None:
        url = os.environ.get("RAGIN_DB_URL", "sqlite:///./ragin_dev.db")
        from ragin.persistence.sql import SqlBackend
        _backend = SqlBackend(url)
    return _backend


def reset_backend() -> None:
    """Clears the active backend — useful in tests."""
    global _backend
    _backend = None
