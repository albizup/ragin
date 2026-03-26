"""ragin start — project scaffolding, Django-style."""
from __future__ import annotations

import os

# ── settings.py template ───────────────────────────────────────────
SETTINGS_TEMPLATE = '''\
"""
ragin settings — edit this file to configure your project.

All UPPER_CASE variables are loaded automatically by the framework.
You can also override any value via environment variables prefixed with RAGIN_,
e.g. RAGIN_DATABASE_URL="postgresql+psycopg2://..." overrides DATABASE_URL below.
"""

# ── Database ────────────────────────────────────────────────────────
# SQLite (local dev — zero setup):
DATABASE_URL = "sqlite:///./ragin_dev.db"

# PostgreSQL (uncomment and fill in):
# DATABASE_URL = "postgresql+psycopg2://user:password@localhost:5432/mydb"

# ── Cloud Provider ──────────────────────────────────────────────────
# "local" for development, or "aws" | "gcp" | "azure" for deploy
PROVIDER = "local"

# ── Dev Server ──────────────────────────────────────────────────────
DEBUG = True
HOST = "127.0.0.1"
PORT = 8000
'''

# ── main.py template ───────────────────────────────────────────────
MAIN_TEMPLATE = '''\
from ragin import ServerlessApp, Field, Model, resource


@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str


# Add more models here:
# @resource(operations=["crud"])
# class Product(Model):
#     id: str = Field(primary_key=True)
#     name: str
#     price: float


app = ServerlessApp()
'''


def scaffold_project(name: str, directory: str | None = None) -> str:
    """
    Create a new ragin project directory with main.py and settings.py.
    Returns the absolute path of the created directory.
    """
    target = os.path.abspath(directory or name)

    if os.path.exists(target) and os.listdir(target):
        # Allow scaffolding into an empty dir or creating a new one
        raise FileExistsError(
            f"Directory '{target}' already exists and is not empty."
        )

    os.makedirs(target, exist_ok=True)

    settings_path = os.path.join(target, "settings.py")
    main_path = os.path.join(target, "main.py")

    with open(settings_path, "w", encoding="utf-8") as f:
        f.write(SETTINGS_TEMPLATE)

    with open(main_path, "w", encoding="utf-8") as f:
        f.write(MAIN_TEMPLATE)

    return target
