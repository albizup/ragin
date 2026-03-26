"""Shared fixtures: isolated registry + in-memory SQLite backend per test."""
import pytest

from ragin.core.registry import registry
from ragin.persistence import configure_backend, reset_backend


@pytest.fixture(autouse=True)
def clean_state():
    """Reset global registry and backend before every test."""
    registry.reset()
    reset_backend()
    configure_backend("sqlite:///:memory:")
    yield
    registry.reset()
    reset_backend()
