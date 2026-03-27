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
