# Ragin — Tutorial completo di tutte le feature

Guida pratica per provare **ogni funzionalità** di ragin, dalla V1 alla V2.
Ogni sezione è un mini-tutorial indipendente con codice pronto da copiare.

---

## Indice

- [0. Setup iniziale](#0-setup-iniziale)
- [1. Scaffold progetto (`ragin start`)](#1-scaffold-progetto)
- [2. Modelli e campi (`Model`, `Field`)](#2-modelli-e-campi)
- [3. Risorse CRUD (`@resource`)](#3-risorse-crud)
- [4. Dev server locale (`ragin dev`)](#4-dev-server-locale)
- [5. Endpoint custom su risorsa](#5-endpoint-custom-su-risorsa)
- [6. Endpoint globali (`@app.get`, `@app.post`)](#6-endpoint-globali)
- [7. Settings e configurazione](#7-settings-e-configurazione)
- [8. Database PostgreSQL](#8-database-postgresql)
- [9. Build per il cloud (`ragin build`)](#9-build-per-il-cloud)
- [10. Agent AI (`@agent`)](#10-agent-ai)
- [11. Custom tools sull'agent](#11-custom-tools-sullagent)
- [12. Agent con più modelli](#12-agent-con-più-modelli)
- [13. Provider LLM (OpenAI, Anthropic, Bedrock)](#13-provider-llm)
- [14. AgentRunner standalone](#14-agentrunner-standalone)
- [15. MCP Server](#15-mcp-server)
- [16. Generazione system prompt](#16-generazione-system-prompt)
- [17. Build CRUD tools manuale](#17-build-crud-tools-manuale)
- [18. Provider LLM custom](#18-provider-llm-custom)
- [19. Test con MockProvider](#19-test-con-mockprovider)

---

## 0. Setup iniziale

```bash
# Clona e installa
cd ragin
uv sync

# Verifica che tutto funzioni
uv run pytest -v
# ✅ 77 tests passed
```

---

## 1. Scaffold progetto

```bash
uv run ragin start mio_progetto
```

Genera questa struttura:

```
mio_progetto/
├── main.py           # App entry point
├── settings.py       # DATABASE_URL, PROVIDER, APP
└── models/
    ├── __init__.py   # from .user import User
    └── user.py       # Modello User di esempio
```

> **Prova**: apri `mio_progetto/main.py` e guarda il codice generato.

---

## 2. Modelli e campi

```python
from ragin import Model, Field

class Product(Model):
    sku: str = Field(primary_key=True)
    name: str
    price: float = Field(description="Prezzo in EUR")
    in_stock: bool = Field(default=True)
    category: str = Field(nullable=True, index=True)

    class Meta:
        table_name = "catalogo"   # opzionale: nome tabella custom
```

**Metodi utili:**
```python
Product.primary_key_field()   # → "sku"
Product.ragin_table_name()    # → "catalogo"
```

**Tipi supportati:** `str`, `int`, `float`, `bool`, `UUID`

**Opzioni Field:**
| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `primary_key` | `False` | Marca come chiave primaria |
| `nullable` | `True` | Permette NULL nel DB |
| `unique` | `False` | Vincolo UNIQUE |
| `index` | `False` | Crea indice nel DB |
| `description` | `None` | Descrizione (usata nei prompt AI) |

---

## 3. Risorse CRUD

```python
from ragin import Model, Field, resource

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str

# Genera automaticamente:
# POST   /users          → 201 Created
# GET    /users          → 200 [lista]
# GET    /users/{id}     → 200 singolo / 404
# PATCH  /users/{id}     → 200 aggiornato / 404
# DELETE /users/{id}     → 204 / 404
```

**Operazioni selettive:**
```python
@resource(operations=["create", "list", "retrieve"])  # solo lettura + creazione
class Log(Model):
    id: str = Field(primary_key=True)
    event: str
```

**Con prefisso path:**
```python
@resource(path_prefix="/api/v2")
class Item(Model):
    id: str = Field(primary_key=True)
    title: str
# → POST /api/v2/items, GET /api/v2/items, ...
```

---

## 4. Dev server locale

```bash
cd mio_progetto
uv run ragin dev
# ⇒ Server listening on http://localhost:8080
```

**Opzioni:**
```bash
uv run ragin dev --port 3000 --host 0.0.0.0
uv run ragin dev --app main:app    # modulo:variabile
```

**Testa con curl:**
```bash
# Crea un utente
curl -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -d '{"id": "u1", "name": "Alice", "email": "alice@example.com"}'

# Lista utenti
curl http://localhost:8080/users

# Singolo utente
curl http://localhost:8080/users/u1

# Aggiorna
curl -X PATCH http://localhost:8080/users/u1 \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Updated"}'

# Lista con filtri
curl "http://localhost:8080/users?limit=10&offset=0&name=Alice"

# Elimina
curl -X DELETE http://localhost:8080/users/u1
```

---

## 5. Endpoint custom su risorsa

```python
from ragin import Model, Field, resource
from ragin.core.responses import InternalResponse

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    active: bool = Field(default=True)

@User.post("/{id}/deactivate")
def deactivate_user(request):
    # request.path_params["id"] contiene l'ID
    return InternalResponse.ok({"deactivated": request.path_params["id"]})

@User.get("/{id}/profile")
def user_profile(request):
    return InternalResponse.ok({"profile": "..."})
```

> **Prova**: `curl -X POST http://localhost:8080/users/u1/deactivate`

---

## 6. Endpoint globali

```python
from ragin import ServerlessApp
from ragin.core.responses import InternalResponse

app = ServerlessApp()

@app.get("/health")
def health(request):
    return InternalResponse.ok({"status": "healthy"})

@app.post("/echo")
def echo(request):
    return InternalResponse.ok(request.json_body)
```

> **Prova**: `curl http://localhost:8080/health`

---

## 7. Settings e configurazione

**`settings.py`** nel tuo progetto:
```python
DATABASE_URL = "sqlite:///./dev.db"
PROVIDER = "local"           # "aws" | "gcp" | "azure" | "local"
APP = "main:app"
```

**Variabili d'ambiente** (override automatico):
```bash
export RAGIN_DATABASE_URL="postgresql+psycopg2://user:pass@localhost/db"
export RAGIN_PROVIDER="aws"
```

**Da codice:**
```python
from ragin.conf import settings

url = settings.DATABASE_URL
settings.configure(DATABASE_URL="sqlite:///:memory:")
settings.reset()
```

---

## 8. Database PostgreSQL

```bash
uv pip install psycopg2-binary
```

In `settings.py`:
```python
DATABASE_URL = "postgresql+psycopg2://user:password@localhost:5432/mydb"
```

Oppure via env:
```bash
export RAGIN_DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/mydb"
```

> Le tabelle vengono create automaticamente al primo utilizzo. Nessuna migration necessaria.

---

## 9. Build per il cloud

```bash
# AWS Lambda
uv run ragin build --provider aws --output dist/

# Google Cloud Functions
uv run ragin build --provider gcp --output dist/

# Azure Functions
uv run ragin build --provider azure --output dist/
```

**Output generato:**
```
dist/
├── handler.py           # Entry point cloud-specifico
├── routes.json          # Mappa dei route
├── _ragin_mcp_entry.py  # Entry MCP (se ci sono agent)
└── requirements.txt     # Dipendenze
```

---

## 10. Agent AI

```python
from ragin import Model, Field, resource, agent
from ragin.providers import OpenAIProvider

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str = Field(description="Indirizzo email dell'utente")

provider = OpenAIProvider(model="gpt-4o", api_key="sk-...")

@agent(model=User, provider=provider, description="Gestisce gli utenti del sistema.")
class UserAgent:
    pass

# Genera automaticamente:
# POST /users/agent  → {"message": "Crea un utente chiamato Alice", "thread_id": "abc"}
#
# Risposta:
# {
#   "message": "Ho creato l'utente Alice con successo!",
#   "tool_calls": [{"tool": "create_user", "arguments": {...}, "result": {...}}],
#   "thread_id": "abc"
# }
```

**Testa con curl:**
```bash
curl -X POST http://localhost:8080/users/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Crea un utente con id u1, nome Alice e email alice@test.com"}'
```

> L'agent genera automaticamente un system prompt che descrive i modelli,
> i campi, i tipi e le descrizioni. Poi usa i tool CRUD per eseguire le operazioni.

---

## 11. Custom tools sull'agent

```python
@agent(model=User, provider=provider)
class UserAgent:
    pass

@UserAgent.tool
def send_welcome_email(user_id: str, subject: str):
    """Invia un'email di benvenuto all'utente."""
    # La tua logica qui
    return {"sent": True, "to": user_id, "subject": subject}

@UserAgent.tool
def count_active_users():
    """Conta gli utenti attivi nel sistema."""
    return {"count": 42}
```

> **Come funziona**: l'LLM vede i tool disponibili (CRUD + custom) e decide
> autonomamente quando chiamarli. I custom tool vengono introspezionati dalla
> firma della funzione Python.

---

## 12. Agent con più modelli

```python
@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str

@resource(operations=["crud"])
class Task(Model):
    id: str = Field(primary_key=True)
    title: str
    assignee: str = Field(description="ID dell'utente assegnato")

@agent(
    model=[User, Task],
    provider=provider,
    description="Gestisci utenti e task del progetto."
)
class ProjectAgent:
    pass

# L'agent ha accesso a TUTTI i tool CRUD di entrambi i modelli:
# create_user, list_users, get_user, update_user, delete_user
# create_task, list_tasks, get_task, update_task, delete_task
```

---

## 13. Provider LLM

### OpenAI
```python
from ragin.providers import OpenAIProvider

provider = OpenAIProvider(
    model="gpt-4o",          # o "gpt-4o-mini", "gpt-4-turbo"
    api_key="sk-...",        # opzionale: usa OPENAI_API_KEY env
)
```
```bash
uv pip install "ragin[openai]"
```

### Anthropic
```python
from ragin.providers import AnthropicProvider

provider = AnthropicProvider(
    model="claude-sonnet-4-20250514",
    api_key="sk-ant-...",   # opzionale: usa ANTHROPIC_API_KEY env
    max_tokens=4096,
)
```
```bash
uv pip install "ragin[anthropic]"
```

### AWS Bedrock
```python
from ragin.providers import BedrockProvider

provider = BedrockProvider(
    model_id="anthropic.claude-sonnet-4-20250514-v1:0",
    region="us-east-1",
    max_tokens=4096,
)
```
```bash
uv pip install "ragin[bedrock]"
# + configura AWS credentials (aws configure)
```

---

## 14. AgentRunner standalone

Usa `AgentRunner` direttamente senza il decorator `@agent`:

```python
from ragin.agent.runner import AgentRunner
from ragin.agent.tools import build_crud_tools
from ragin.providers import OpenAIProvider

provider = OpenAIProvider(model="gpt-4o")
tools = build_crud_tools(User)

runner = AgentRunner(
    provider=provider,
    system_prompt="Sei un assistente che gestisce utenti.",
    tools=tools,
)

# Registra tool custom
def notify(user_id: str):
    """Invia una notifica."""
    return f"Notificato {user_id}"

runner.register_custom_tool(notify)

# Esegui
result = runner.run("Crea l'utente Bob e notificalo", thread_id="conv-1")
print(result["message"])
print(result["tool_calls"])
```

> **Loop interno**: il runner chiama l'LLM → se ritorna tool_calls li esegue →
> rimanda i risultati all'LLM → ripete fino a risposta finale (max 10 iterazioni).

---

## 15. MCP Server

Esponi i tool CRUD come **Model Context Protocol** server per IDE e altri client:

```python
from ragin.agent.tools import build_crud_tools
from ragin.mcp import MCPServer

tools = build_crud_tools(User) + build_crud_tools(Task)
mcp = MCPServer(tools)

# Gestisci richieste JSON-RPC
response = mcp.handle({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize"
})
# → {"result": {"protocolVersion": "2025-03-26", "serverInfo": {"name": "ragin-mcp"}}}

response = mcp.handle({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list"
})
# → {"result": {"tools": [{"name": "create_user", "inputSchema": {...}}, ...]}}

response = mcp.handle({
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {"name": "create_user", "arguments": {"id": "u1", "name": "Alice"}}
})
# → {"result": {"content": [{"type": "text", "text": "{...}"}]}}
```

> **Nel build**: se hai `@agent`, `ragin build` genera automaticamente
> `_ragin_mcp_entry.py` con un endpoint Lambda per MCP.

---

## 16. Generazione system prompt

```python
from ragin.agent.prompt import generate_system_prompt

prompt = generate_system_prompt(
    [User, Task],
    description="Aiuta a gestire il progetto."
)
print(prompt)
```

**Output esempio:**
```
You are an AI assistant. Aiuta a gestire il progetto.

You have access to the following data models:

## User (table: users)
- id: str (primary key)
- name: str
- email: str — Indirizzo email dell'utente

## Task (table: tasks)
- id: str (primary key)
- title: str
- assignee: str — ID dell'utente assegnato

Use the available tools to perform operations on these models.
```

---

## 17. Build CRUD tools manuale

```python
from ragin.agent.tools import build_crud_tools, ToolDefinition

# Tutti e 5 i tool CRUD
tools = build_crud_tools(User)
for t in tools:
    print(f"{t.name}: {t.description}")
    print(f"  params: {t.parameters}")

# Solo alcuni
tools = build_crud_tools(User, operations=["create", "list"])

# Esecuzione diretta di un tool
create = next(t for t in tools if "create" in t.name)
result = create.handler({"id": "u1", "name": "Alice", "email": "a@a.com"})
print(result)  # → {"id": "u1", "name": "Alice", "email": "a@a.com"}
```

---

## 18. Provider LLM custom

Crea il tuo provider implementando `BaseProvider`:

```python
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall

class MistralProvider(BaseProvider):
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key

    def complete(self, messages, tools=None):
        # Chiama la tua API qui
        # ...
        # Se l'LLM vuole chiamare un tool:
        return AgentResponse(tool_calls=[
            ToolCall(id="tc-1", name="create_user", arguments={"id": "u1", "name": "Bob"})
        ])
        # Se l'LLM vuole rispondere:
        return AgentResponse(content="Fatto!")

# Usalo come qualsiasi altro provider
@agent(model=User, provider=MistralProvider("mistral-large", "..."))
class UserAgent:
    pass
```

---

## 19. Test con MockProvider

Per testare senza chiamare API reali:

```python
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall

class MockProvider(BaseProvider):
    """Ritorna risposte predefinite in ordine."""
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0

    def complete(self, messages, tools=None):
        resp = self._responses[self._idx]
        self._idx += 1
        return resp

# Test: l'agent crea un utente e risponde
mock = MockProvider([
    # Prima chiamata: l'LLM decide di creare l'utente
    AgentResponse(tool_calls=[
        ToolCall(id="tc1", name="create_user", arguments={
            "id": "u1", "name": "Alice", "email": "alice@test.com"
        })
    ]),
    # Seconda chiamata: l'LLM risponde con il risultato
    AgentResponse(content="Ho creato l'utente Alice!"),
])

@agent(model=User, provider=mock)
class TestAgent:
    pass

# Ora puoi testare l'endpoint /users/agent senza spendere token!
```

---

## Checklist rapida

| # | Feature | Comando/File | Provata? |
|---|---------|-------------|----------|
| 1 | Scaffold | `ragin start mioprogetto` | ☐ |
| 2 | Modelli & Field | `Model`, `Field(primary_key=True)` | ☐ |
| 3 | CRUD auto | `@resource(operations=["crud"])` | ☐ |
| 4 | Dev server | `ragin dev` | ☐ |
| 5 | Endpoint custom risorsa | `@User.post("/{id}/action")` | ☐ |
| 6 | Endpoint globali | `@app.get("/health")` | ☐ |
| 7 | Settings | `settings.py` + env vars | ☐ |
| 8 | PostgreSQL | `DATABASE_URL = "postgresql+..."` | ☐ |
| 9 | Build cloud | `ragin build --provider aws` | ☐ |
| 10 | Agent AI | `@agent(model=User, provider=...)` | ☐ |
| 11 | Custom tools | `@UserAgent.tool` | ☐ |
| 12 | Multi-model agent | `@agent(model=[User, Task])` | ☐ |
| 13 | Provider OpenAI | `OpenAIProvider(model="gpt-4o")` | ☐ |
| 14 | Provider Anthropic | `AnthropicProvider(model="...")` | ☐ |
| 15 | Provider Bedrock | `BedrockProvider(model_id="...")` | ☐ |
| 16 | AgentRunner standalone | `AgentRunner(provider, prompt, tools)` | ☐ |
| 17 | MCP Server | `MCPServer(tools)` | ☐ |
| 18 | System prompt gen | `generate_system_prompt([User])` | ☐ |
| 19 | CRUD tools manuali | `build_crud_tools(User)` | ☐ |
| 20 | Provider custom | `class MyProvider(BaseProvider)` | ☐ |
| 21 | MockProvider test | `MockProvider([AgentResponse(...)])` | ☐ |
