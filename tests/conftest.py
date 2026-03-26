"""Shared fixtures: isolated registry + in-memory SQLite backend per test."""
import pytest

from ragin.conf import settings
from ragin.core.registry import registry
from ragin.persistence import configure_backend, reset_backend


@pytest.fixture(autouse=True)
def clean_state():
    """Reset global registry, backend, and settings before every test."""
    registry.reset()
    reset_backend()
    settings.reset()
    configure_backend("sqlite:///:memory:")
    yield
    registry.reset()
    reset_backend()
    settings.reset()
