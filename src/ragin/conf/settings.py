"""
ragin settings loader.

Works like Django: a Python module pointed to by RAGIN_SETTINGS_MODULE env var
(default: "settings"). The module is imported and its UPPER_CASE attributes
become the active configuration.

Precedence (highest → lowest):
    1. Explicit configure_settings() call
    2. RAGIN_SETTINGS_MODULE env var → import that module
    3. Built-in defaults
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import Any

_DEFAULTS: dict[str, Any] = {
    "DATABASE_URL": "sqlite:///./ragin_dev.db",
    "PROVIDER": "local",
    "DEBUG": True,
    "HOST": "127.0.0.1",
    "PORT": 8000,
    "APP": "main:app",
}


class Settings:
    """Lazy settings container — loads the settings module on first attribute access."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._store = dict(_DEFAULTS)

        module_name = os.environ.get("RAGIN_SETTINGS_MODULE", "settings")
        try:
            # Ensure CWD is on the path so `import settings` works
            if "." not in sys.path and "" not in sys.path:
                sys.path.insert(0, "")
            mod = importlib.import_module(module_name)
            for key in dir(mod):
                if key.isupper():
                    self._store[key] = getattr(mod, key)
        except ModuleNotFoundError:
            pass  # no settings module → use defaults + env overrides

        # Env vars override: RAGIN_DATABASE_URL, RAGIN_PROVIDER, etc.
        for key in _DEFAULTS:
            env_val = os.environ.get(f"RAGIN_{key}")
            if env_val is not None:
                # Cast to the same type as default
                default = _DEFAULTS[key]
                if isinstance(default, bool):
                    self._store[key] = env_val.lower() in ("1", "true", "yes")
                elif isinstance(default, int):
                    self._store[key] = int(env_val)
                else:
                    self._store[key] = env_val

        # Legacy env var support
        if "RAGIN_DB_URL" in os.environ and "RAGIN_DATABASE_URL" not in os.environ:
            self._store["DATABASE_URL"] = os.environ["RAGIN_DB_URL"]

        self._loaded = True

    def configure(self, overrides: dict[str, Any]) -> None:
        """Programmatic override — e.g. in tests."""
        self._load()
        self._store.update(overrides)

    def reset(self) -> None:
        """Reset to un-loaded state (for tests)."""
        self._store = {}
        self._loaded = False

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        self._load()
        try:
            return self._store[name]
        except KeyError:
            raise AttributeError(f"Setting {name!r} not found")

    def __repr__(self) -> str:
        self._load()
        return f"<Settings {self._store}>"


settings = Settings()
