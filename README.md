<p align="center">
  <img src="ragin_logo.png" alt="Ragin" width="400">
</p>

<p align="center">
  <strong>Model-First Serverless Framework for Python</strong><br>
  Define your models once. Get CRUD endpoints, database schema, and cloud deployment — automatically.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/pydantic-v2-e92063?logo=pydantic&logoColor=white" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/cloud-agnostic-orange" alt="Cloud Agnostic">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
</p>

---

## What is Ragin?

Ragin is a Python framework where you **define a model once** and everything else is generated: REST endpoints, database tables, and serverless deployment entry points. Think Django's model layer married with FastAPI's developer experience, built for serverless from day one.

```python
from ragin import ServerlessApp, Field, Model, resource

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str

app = ServerlessApp()
```

That's it. You now have `POST /users`, `GET /users`, `GET /users/{id}`, `PATCH /users/{id}`, `DELETE /users/{id}` — with validation, persistence, and proper HTTP status codes.

## Quick Start

### 1. Install

```bash
pip install ragin
# or with uv
uv add ragin
```

### 2. Scaffold a project

```bash
ragin start myproject
cd myproject
```

This generates:

```
myproject/
├── main.py              # App entry point
├── settings.py          # Database, provider, server config
└── models/
    ├── __init__.py      # Model registry
    └── user.py          # Example User model
```

### 3. Run locally

```bash
ragin dev
```

Server starts at `http://127.0.0.1:8000`. Hit your endpoints:

```bash
# Create
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"id": "u1", "name": "Alice", "email": "alice@example.com"}'

# List
curl http://localhost:8000/users

# Retrieve
curl http://localhost:8000/users/u1

# Update
curl -X PATCH http://localhost:8000/users/u1 \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Updated"}'

# Delete
curl -X DELETE http://localhost:8000/users/u1
```

## Configuration

Ragin uses a `settings.py` file — Django-style. Every setting can be overridden via environment variables prefixed with `RAGIN_`.

```python
# settings.py

DATABASE_URL = "sqlite:///./ragin_dev.db"    # or postgresql+psycopg2://...
PROVIDER = "local"                           # local | aws | gcp | azure
DEBUG = True
HOST = "127.0.0.1"
PORT = 8000
```

**Precedence** (highest wins):

| Priority | Source |
|----------|--------|
| 1 | Environment variables (`RAGIN_DATABASE_URL`, …) |
| 2 | `settings.py` |
| 3 | Built-in defaults |

### Database

SQLite works out of the box for development. For production, switch to PostgreSQL:

```bash
uv add ragin[postgres]
```

```python
# settings.py
DATABASE_URL = "postgresql+psycopg2://user:password@host:5432/mydb"
```

Tables are created automatically on first request.

## Models & Resources

### Defining a model

```python
from ragin import Field, Model, resource

@resource(operations=["crud"])
class Product(Model):
    id: str = Field(primary_key=True)
    name: str
    price: float
    in_stock: bool = True
```

The `@resource` decorator auto-generates 5 endpoints:

| Method | Path | Operation |
|--------|------|-----------|
| `POST` | `/products` | Create |
| `GET` | `/products` | List (supports `?limit=N&offset=N`) |
| `GET` | `/products/{id}` | Retrieve |
| `PATCH` | `/products/{id}` | Update |
| `DELETE` | `/products/{id}` | Delete |

### Field options

```python
id: str    = Field(primary_key=True)
email: str = Field(unique=True)
name: str  = Field(index=True)
bio: str   = Field(nullable=True)
```

### Selective operations

```python
@resource(operations=["create", "list", "retrieve"])  # read-heavy, no update/delete
class Article(Model):
    ...
```

### Custom table name

```python
@resource(operations=["crud"])
class User(Model):
    class Meta:
        table_name = "app_users"

    id: str = Field(primary_key=True)
    name: str
```

### Custom endpoints

```python
app = ServerlessApp()

# Global custom endpoint
@app.get("/health")
def health(request):
    from ragin.core.responses import InternalResponse
    return InternalResponse.ok({"status": "healthy"})
```

## Project Structure

A typical ragin project:

```
myproject/
├── main.py              # ServerlessApp + imports
├── settings.py          # Configuration
└── models/
    ├── __init__.py      # from models.user import User, etc.
    ├── user.py
    └── product.py       # Add models as you go
```

**Adding a new model:**

1. Create `models/order.py` with your `@resource` class
2. Import it in `models/__init__.py`
3. Done — endpoints are live on next request

## Cloud Deployment

Ragin is cloud-agnostic. The same code runs on AWS, GCP, or Azure.

### Build for production

```bash
ragin build --provider aws      # generates Lambda + API Gateway entry
ragin build --provider gcp      # generates Cloud Functions entry
ragin build --provider azure    # generates Azure Functions entry
```

This creates a `build/` directory with the cloud-specific entry point and route manifest. Your `main.py` never changes.

### Provider architecture

```
Your Code (main.py)
       │
       ▼
  ServerlessApp
       │
       ▼
  RuntimeProvider ──► AWSProvider   (API Gateway → Lambda)
                  ──► GCPProvider   (Cloud Functions)
                  ──► AzureProvider (Azure Functions)
                  ──► LocalProvider (Werkzeug dev server)
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `ragin start <name>` | Scaffold a new project |
| `ragin dev` | Start the local dev server |
| `ragin build --provider <aws\|gcp\|azure>` | Generate deployment entry point |

```bash
# Dev server with custom host/port
ragin dev --host 0.0.0.0 --port 3000

# Specify a different app module
ragin dev --app myapp:application

# Build for AWS
ragin build --provider aws --output dist
```

## Tech Stack

- **[Pydantic v2](https://docs.pydantic.dev/)** — Model validation
- **[SQLAlchemy Core 2.0](https://www.sqlalchemy.org/)** — Database layer (no ORM)
- **[Click](https://click.palletsprojects.com/)** — CLI
- **[Werkzeug](https://werkzeug.palletsprojects.com/)** — Local dev server

## Roadmap

- [x] **V1** — Model-first CRUD, cloud-agnostic runtime, settings system
- [ ] **V2** — `@agent` decorator for AI agents with multi-provider LLM support
- [ ] **V3** — MCP (Model Context Protocol) tools auto-generated from models

## License

MIT