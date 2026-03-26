<p align="center">
  <img src="ragin_logo.png" alt="Ragin" width="400">
</p>

<p align="center">
  <strong>Model-First Serverless Framework for Python</strong><br>
  Define your models once. Get CRUD endpoints, AI agents, MCP tools, and cloud deployment — automatically.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/pydantic-v2-e92063?logo=pydantic&logoColor=white" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/cloud-agnostic-orange" alt="Cloud Agnostic">
  <img src="https://img.shields.io/badge/AI-agents-blueviolet" alt="AI Agents">
  <img src="https://img.shields.io/badge/MCP-server-teal" alt="MCP Server">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
</p>

---

## What is Ragin?

Ragin is a Python framework where you **define a model once** and everything else is generated: REST endpoints, database tables, AI agents with tool calling, MCP server, and serverless deployment entry points. Think Django's model layer married with FastAPI's developer experience, built for serverless from day one.

```python
from ragin import ServerlessApp, Field, Model, resource, agent
from ragin.providers import OpenAIProvider

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str = Field(description="User email address")

@agent(model=User, provider=OpenAIProvider(model="gpt-4o"))
class UserAgent:
    pass

app = ServerlessApp()
```

That's it. You now have:
- **5 CRUD endpoints** — `POST /users`, `GET /users`, `GET /users/{id}`, `PATCH /users/{id}`, `DELETE /users/{id}`
- **1 AI agent endpoint** — `POST /users/agent` that understands natural language and calls CRUD tools automatically
- **Validation, persistence, and proper HTTP status codes** out of the box

## Quick Start

### 1. Install

```bash
pip install ragin
# or with uv
uv add ragin

# Optional: install an LLM provider for AI agents
uv add "ragin[openai]"      # OpenAI
uv add "ragin[anthropic]"   # Anthropic
uv add "ragin[bedrock]"     # AWS Bedrock
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

# List with filters
curl "http://localhost:8000/users?limit=10&offset=0&name=Alice"

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
| `GET` | `/products` | List (supports `?limit=N&offset=N` + field filters) |
| `GET` | `/products/{id}` | Retrieve |
| `PATCH` | `/products/{id}` | Update |
| `DELETE` | `/products/{id}` | Delete |

### Field options

```python
id: str    = Field(primary_key=True)
email: str = Field(unique=True)
name: str  = Field(index=True)
bio: str   = Field(nullable=True)
role: str  = Field(description="Used in AI agent prompts")
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
from ragin.core.responses import InternalResponse

# Global custom endpoint
app = ServerlessApp()

@app.get("/health")
def health(request):
    return InternalResponse.ok({"status": "healthy"})

# Resource-scoped custom endpoint
@User.post("/{id}/deactivate")
def deactivate(request):
    return InternalResponse.ok({"deactivated": request.path_params["id"]})
```

## AI Agents

Wire an LLM-powered agent to any model with a single decorator. The agent auto-generates a system prompt from your model schema and exposes CRUD operations as tools the LLM can call.

### Basic agent

```python
from ragin import Model, Field, resource, agent
from ragin.providers import OpenAIProvider

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str = Field(description="User email address")

@agent(
    model=User,
    provider=OpenAIProvider(model="gpt-4o"),
    description="Manages user records.",
)
class UserAgent:
    pass
```

This creates `POST /users/agent`:

```bash
curl -X POST http://localhost:8000/users/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a user named Alice with email alice@test.com"}'
```

Response:

```json
{
  "message": "I've created the user Alice with email alice@test.com.",
  "tool_calls": [
    {
      "tool": "create_user",
      "arguments": {"id": "...", "name": "Alice", "email": "alice@test.com"},
      "result": {"id": "...", "name": "Alice", "email": "alice@test.com"}
    }
  ],
  "thread_id": null
}
```

### Custom tools

Add domain-specific tools beyond CRUD:

```python
@agent(model=User, provider=provider)
class UserAgent:
    pass

@UserAgent.tool
def send_welcome_email(user_id: str, subject: str):
    """Send a welcome email to the user."""
    return {"sent": True, "to": user_id}
```

The LLM sees all tools (CRUD + custom) and decides when to call them.

### Multi-model agent

```python
@resource(operations=["crud"])
class Task(Model):
    id: str = Field(primary_key=True)
    title: str
    assignee: str = Field(description="User ID of the assignee")

@agent(
    model=[User, Task],
    provider=provider,
    description="Manage users and their tasks.",
)
class ProjectAgent:
    pass
# Has access to all 10 CRUD tools: create_user, list_users, ..., create_task, list_tasks, ...
```

### LLM Providers

```python
from ragin.providers import OpenAIProvider, AnthropicProvider, BedrockProvider

# OpenAI
provider = OpenAIProvider(model="gpt-4o")                    # uses OPENAI_API_KEY env

# Anthropic
provider = AnthropicProvider(model="claude-sonnet-4-20250514")        # uses ANTHROPIC_API_KEY env

# AWS Bedrock
provider = BedrockProvider(model_id="anthropic.claude-sonnet-4-20250514-v1:0", region="us-east-1")
```

Install the provider you need:

```bash
uv add "ragin[openai]"      # pip install ragin[openai]
uv add "ragin[anthropic]"   # pip install ragin[anthropic]
uv add "ragin[bedrock]"     # pip install ragin[bedrock]
```

### Custom provider

```python
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall

class MyProvider(BaseProvider):
    def complete(self, messages, tools=None):
        # Call your LLM API...
        return AgentResponse(content="Done!")
        # Or request tool calls:
        return AgentResponse(tool_calls=[
            ToolCall(id="tc-1", name="create_user", arguments={...})
        ])
```

### AgentRunner standalone

Use the runner directly without the `@agent` decorator:

```python
from ragin.agent.runner import AgentRunner
from ragin.agent.tools import build_crud_tools

tools = build_crud_tools(User)
runner = AgentRunner(provider=provider, system_prompt="You manage users.", tools=tools)

result = runner.run("Create user Bob", thread_id="conv-1")
print(result["message"])
```

## MCP Server

Ragin auto-generates an [MCP](https://modelcontextprotocol.io) server that exposes your CRUD operations as MCP tools — consumable by Claude Desktop, VS Code, or any MCP client.

```python
from ragin.agent.tools import build_crud_tools
from ragin.mcp import MCPServer

tools = build_crud_tools(User)
mcp = MCPServer(tools)

# Handle JSON-RPC requests
response = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
response = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
response = mcp.handle({
    "jsonrpc": "2.0", "id": 3,
    "method": "tools/call",
    "params": {"name": "create_user", "arguments": {"id": "u1", "name": "Alice"}}
})
```

When you `ragin build` with agents defined, an MCP Lambda entry point is generated automatically.

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

This creates a `build/` directory with:

```
build/
├── _ragin_entry.py        # Cloud-specific entry point (CRUD + agent routes)
├── _ragin_mcp_entry.py    # MCP server entry (if agents are defined)
└── routes.json            # Route manifest with crud/agent/mcp sections
```

Your `main.py` never changes.

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

## Testing

Ragin is designed for easy testing. Use `MockProvider` to test agents without hitting real LLM APIs:

```python
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall

class MockProvider(BaseProvider):
    def __init__(self, responses):
        self._responses = iter(responses)

    def complete(self, messages, tools=None):
        return next(self._responses)

mock = MockProvider([
    AgentResponse(tool_calls=[
        ToolCall(id="tc1", name="create_user", arguments={"id": "u1", "name": "Alice", "email": "a@a.com"})
    ]),
    AgentResponse(content="Created Alice!"),
])

@agent(model=User, provider=mock)
class TestAgent:
    pass
```

## Tech Stack

- **[Pydantic v2](https://docs.pydantic.dev/)** — Model validation
- **[SQLAlchemy Core 2.0](https://www.sqlalchemy.org/)** — Database layer (no ORM)
- **[Click](https://click.palletsprojects.com/)** — CLI
- **[Werkzeug](https://werkzeug.palletsprojects.com/)** — Local dev server
- **[OpenAI](https://platform.openai.com/)** / **[Anthropic](https://www.anthropic.com/)** / **[AWS Bedrock](https://aws.amazon.com/bedrock/)** — LLM providers (optional)

## Roadmap

- [x] **V1** — Model-first CRUD, cloud-agnostic runtime, settings system, scaffolding
- [x] **V2** — `@agent` decorator, multi-provider LLM (OpenAI, Anthropic, Bedrock), MCP server, tool binding
- [ ] **V3** — Streaming responses, persistent conversation history, hooks, auth/permissions

## License

MIT