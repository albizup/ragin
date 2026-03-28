# ragin — Design Document

> Model-First · Serverless-First · AI-Native

---

## 1. Vision

**ragin** è un framework Python che permette di definire un modello Pydantic una volta sola
e ottenere automaticamente:

- endpoint HTTP CRUD serverless (AWS Lambda + API Gateway)
- schema database
- un **AI agent serverless** con tool binding automatico sugli endpoint generati
- un **MCP server serverless** che espone i tool dell'agente via HTTP
- **semantic search** automatica con embeddings e vector store

L'obiettivo è abbassare a zero il boilerplate per costruire API + AI agent su infrastruttura
serverless, mantenendo la flessibilità di override su ogni livello.

---

## 2. Principi Core

### 2.1 Model as Single Source of Truth
Il modello Pydantic guida tutto: schema DB, validazione, routing, tool schema MCP,
system prompt dell'agente.

### 2.2 Serverless First
Non esiste un server HTTP tradizionale. Tutto gira su Lambda (o equivalenti cloud).
L'agente AI non fa eccezione: è una Lambda, e i tool che chiama sono Lambda.

### 2.3 MCP Serverless
I tool dell'agente sono esportati come **MCP server serverless** — una Lambda dedicata
che implementa il protocollo MCP over Streamable HTTP. L'agente chiama i tool via HTTP,
tutto rimane stateless e scalabile.

### 2.4 Multi-Provider LLM
`@agent` non è legato a un solo modello LLM. Il provider è un parametro esplicito e
ragin supporta più backend tramite adapter intercambiabili.

### 2.5 Automatic by Default, Explicit When Needed
CRUD automatico, agent automatico. Ogni parte è sovrascrivibile.

---

## 3. Quick Example

```python
from ragin import ServerlessApp, Model, Field, resource, agent
from ragin.providers import OpenAIProvider

app = ServerlessApp()


@agent(
    provider=OpenAIProvider(model="gpt-4o"),
    description="Manages user records. Can create, list, retrieve, update and delete users.",
)
@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str
    bio: str = Field(embedding=True)   # V3: auto-embedding per semantic search
    role: str = "member"
```

Quello che viene generato automaticamente:

| Layer         | Output                                                        |
|---------------|---------------------------------------------------------------|
| Database      | Tabella `users` con colonne tipizzate                         |
| CRUD API      | `POST/GET /users`, `GET/PATCH/DELETE /users/{id}`             |
| MCP Server    | Lambda MCP con tool `create_user`, `list_users`, ecc.         |
| Agent         | Lambda agent su `POST /users/agent`                           |
| Semantic      | Tool `semantic_search_users` + embedding pipeline auto (V3)   |
| System Prompt | Generato dallo schema del modello + `description`             |
| OpenAPI       | `openapi.json` completo                                       |

---

## 4. Architettura

### 4.1 Vista ad alto livello

```
Client
  │
  ▼
API Gateway
  ├── /users           →  CRUD Lambda
  ├── /users/{id}      →  CRUD Lambda
  ├── /users/agent     →  Agent Lambda  (CRUD tools + semantic tools)
  ├── /users/search    →  Semantic Search Lambda  (V3)
  └── /mcp            →  MCP Lambda
```

Ogni blocco è una Lambda indipendente. Non c'è un server condiviso.

### 4.1b Layered Architecture

```
┌──────────────────────────────────────────────┐
│  Layer 3 — Semantic (V3)                     │
│  Field(embedding=True) → EmbeddingProvider   │
│  → VectorBackend → semantic_search tools     │
├──────────────────────────────────────────────┤
│  Layer 2 — Agent (V2)                        │
│  @agent → LLM Provider → AgentRunner         │
│  → Tool Registry → MCP Server                │
├──────────────────────────────────────────────┤
│  Layer 1 — Core (V1)                         │
│  Model → Field → @resource → CRUD            │
│  → SqlBackend → Runtime Provider             │
└──────────────────────────────────────────────┘
```

### 4.2 CRUD Lambda

```
API Gateway event
  ↓
app.handle(event, context)
  ↓
InternalRouter
  ↓
Generated Handler  ←→  Database
  ↓
InternalResponse → Lambda response
```

Single Lambda handler, internal router, generato da `app.register(Model)`.

### 4.3 Agent Lambda

```
POST /players/agent  {"message": "lista i giocatori con più di 25 anni"}
  ↓
Agent Lambda
  ↓
LLM Provider (OpenAI / Anthropic / Bedrock / ...)
  ↓  tool_call: list_players(age__gt=25)
MCP Lambda  ←→  CRUD Lambda  ←→  Database
  ↓
LLM → risposta finale
  ↓
Response
```

L'agente non ha stato. Ogni invocazione è indipendente (conversazione stateless by default,
con opzione di passare `thread_id` per history esterna).

### 4.4 MCP Lambda

Il MCP server è una Lambda separata che implementa il protocollo
[Model Context Protocol](https://modelcontextprotocol.io) via **Streamable HTTP**.

- Espone i tool generati automaticamente dai modelli registrati
- Ogni tool corrisponde a un'operazione CRUD (o custom)
- L'agente lo chiama come client MCP standard
- È anche consumabile da qualsiasi client MCP esterno (Claude Desktop, Cursor, ecc.)

```
MCP Lambda espone:
  tools/list   → elenco tool generati da Player, ...
  tools/call   → esegue il tool (chiama CRUD Lambda internamente)
```

Questo separa la logica di tool execution dal LLM, rende i tool riusabili,
e mantiene tutto serverless.

---

## 5. Model Layer

### Definizione

```python
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str = Field(unique=True)
    bio: str = Field(embedding=True)   # V3: genera embedding automatico
    role: str = "member"
```

### Naming

Di default, sia il nome tabella che il nome endpoint usano la **pluralizzazione smart**
del nome classe in lowercase (es. `User` → `users`, `Category` → `categories`).
Customizzabili via inner class `Meta`:

```python
class User(Model):
    class Meta:
        table_name = "app_users"      # DB table (default: "users")
        endpoint_name = "people"       # REST path (default: "users")

    id: str = Field(primary_key=True)
    name: str
```

Metodi: `Model.ragin_table_name()`, `Model.ragin_endpoint_name()`.

### Field Options

```python
Field(
    primary_key=False,
    nullable=True,
    default=None,
    unique=False,
    index=False,
    description="",   # usato nel system prompt dell'agente
    embedding=False,   # V3: se True, genera embedding per semantic search
)
```

---

## 6. Resource Layer

### Decorator

```python
@resource(
    name="users",                                              # default: _pluralize(cls.__name__.lower())
    operations=["create", "list", "retrieve", "update", "delete"],  # oppure: ["crud"]
    path_prefix="/v1",                                         # opzionale
)
class User(Model):
    ...
```

### Operazioni generate

| Operation  | Method | Path              |
|------------|--------|-------------------|
| `create`   | POST   | `/users`          |
| `list`     | GET    | `/users`          |
| `retrieve` | GET    | `/users/{id}`     |
| `update`   | PATCH  | `/users/{id}`     |
| `delete`   | DELETE | `/users/{id}`     |

Il path parameter per retrieve/update/delete usa il nome del campo primary key.
Se il PK si chiama `player_id`, il path sarà `/players/{player_id}`.

### Error Handling

| Scenario            | Status | Body                                    |
|---------------------|--------|-----------------------------------------|
| Validation error    | 400    | `{"error": [...pydantic errors...]}`    |
| Not found           | 404    | `{"error": "Not found"}`               |
| Duplicate PK        | 409    | `{"error": "Resource with that key already exists."}` |
| Internal error      | 500    | `{"error": "Internal server error"}`   |

### Endpoint custom

```python
# globale
@app.get("/health")
def health(request):
    return {"ok": True}

# resource-specific
@User.get("/{id}/profile")
def user_profile(request):
    return {"user_id": request.path_params["id"]}
```

### Hooks (V2+)

```python
@hook(User, "before_create")
def validate_email(data: User) -> User:
    if "@" not in data.email:
        raise ValidationError("Invalid email")
    return data
```

---

## 7. Agent Layer

### Decorator

```python
# Stacking diretto su @resource (consigliato):
@agent(provider=OpenAIProvider(...), description="...")
@resource(operations=["crud"])
class User(Model): ...

# Oppure, con classe agente separata (legacy):
@agent(
    model=User,                          # modello di riferimento (o lista di modelli)
    provider=OpenAIProvider(...),        # LLM provider
    description="...",                   # aggiunto al system prompt
    tools=["crud"],                      # tool abilitati: "crud", lista operazioni, o custom
    history_backend=None,                # None = stateless, "dynamodb" = history persistente
)
class UserAgent:
    pass
```

L'agente genera automaticamente:
- **system prompt** dal nome del modello, campi, descrizioni dei Field e `description`
- **tool schema** MCP per ogni operazione abilitata
- **endpoint** `POST /users/agent`
- **registrazione tool** nel registro globale (`ResourceRegistry._tools`)

### Request/Response

```python
# Request
POST /users/agent
{
  "message": "Crea un utente Alice con email alice@example.com e ruolo admin",
  "thread_id": "abc123"    // opzionale, per history
}

# Response
{
  "message": "Ho creato l'utente Alice con successo.",
  "tool_calls": [...],     // opzionale, per debug
  "thread_id": "abc123"
}
```

### Tool custom per l'agente

```python
@UserAgent.tool
def users_by_role(role: str, limit: int = 10) -> list[dict]:
    """Ritorna gli utenti con un dato ruolo."""
    ...
```

Il tool viene aggiunto automaticamente al registro globale, condiviso con il MCP server.

---

## 8. Multi-Provider LLM

ragin non implementa un proprio client LLM. Si appoggia su framework esistenti
tramite adapter, scelto al momento della definizione dell'agente.

### Provider built-in

```python
from ragin.providers import (
    OpenAIProvider,        # openai SDK
    AnthropicProvider,     # anthropic SDK
    BedrockProvider,       # boto3 / AWS Bedrock
    LangChainProvider,     # qualsiasi LangChain chat model
    PydanticAIProvider,    # pydantic-ai agent
)
```

### Esempi

```python
# OpenAI
@agent(model=Player, provider=OpenAIProvider(model="gpt-4o", api_key="..."))

# Anthropic
@agent(model=Player, provider=AnthropicProvider(model="claude-3-5-sonnet-20241022"))

# AWS Bedrock
@agent(model=Player, provider=BedrockProvider(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0"))

# LangChain (qualsiasi modello supportato)
from langchain_openai import ChatOpenAI
@agent(model=Player, provider=LangChainProvider(llm=ChatOpenAI(model="gpt-4o")))
```

### Custom Provider

```python
from ragin.providers.base import BaseProvider

class MyProvider(BaseProvider):
    def complete(self, messages: list, tools: list) -> AgentResponse:
        ...
```

---

## 9. MCP Serverless — Dettagli

### Perché MCP come Lambda separata

- I tool sono riusabili da qualsiasi client MCP (non solo l'agente ragin)
- Separazione di responsabilità: l'agente non conosce il DB, chiama tool via HTTP
- Scalabilità indipendente: la Lambda MCP scala separatamente dalla Lambda agente
- Sicurezza: la Lambda CRUD non è esposta direttamente all'agente

### Tool generati automaticamente

Per ogni modello registrato con `@resource`, il MCP server espone:

```
create_player(name: str, age: int, team: str) → Player
list_player(filters: dict, limit: int, offset: int) → list[Player]
get_player(id: UUID) → Player
update_player(id: UUID, data: dict) → Player
delete_player(id: UUID) → bool
```

Il JSON schema di ogni tool è derivato dal modello Pydantic (stessa definizione usata
per la validazione CRUD).

### Flusso interno MCP

```
Agent Lambda
  │  HTTP POST /mcp/tools/call  {"name": "list_player", "arguments": {...}}
  ▼
MCP Lambda
  │  Risolve il tool → chiama CRUD Lambda internamente (invoke diretto o HTTP)
  ▼
CRUD Lambda → DB
  │
  ▼
MCP Lambda → risposta JSON al formato MCP
  │
  ▼
Agent Lambda → passa risultato al LLM
```

### Consumo esterno

Il MCP server ragin è compatibile con qualsiasi client MCP standard:

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "ragin-players": {
      "url": "https://abc123.execute-api.eu-west-1.amazonaws.com/mcp"
    }
  }
}
```

---

## 10. Deployment

### CLI

```bash
ragin start myproject # scaffold nuovo progetto con main.py, settings.py, models/
ragin dev             # server locale per sviluppo (legge settings.py)
ragin build           # pacchetto Lambda, routes.json, openapi.json, mcp-manifest.json
ragin deploy          # deploy su AWS (CDK under the hood) — futuro
```

### Output di `ragin build`

```
build/
  lambda_crud.zip
  lambda_agent.zip
  lambda_mcp.zip
  routes.json
  openapi.json
  mcp-manifest.json
```

### routes.json

```json
{
  "lambdas": {
    "crud":  { "handler": "main.lambda_handler", "routes": [...] },
    "agent": { "handler": "main.agent_handler",  "routes": [{"method": "POST", "path": "/player/agent"}] },
    "mcp":   { "handler": "main.mcp_handler",    "routes": [{"method": "POST", "path": "/mcp"}] }
  }
}
```

### Infrastruttura (AWS CDK / Terraform)

ragin genera i file di infrastruttura. Il deploy crea:

- **3 Lambda** (crud, agent, mcp) con IAM roles minimi
- **1 API Gateway HTTP** con le route mappate
- **1 tabella RDS / DynamoDB** (configurabile)
- Variabili d'ambiente per le API key LLM (da AWS Secrets Manager)

---

## 11. Struttura del Framework

```
ragin/
  core/
    app.py            # ServerlessApp
    models.py         # Model base class
    fields.py         # Field
    routing.py        # RouteDefinition, Router
    registry.py       # registro globale di modelli, agenti, tool
    requests.py       # InternalRequest (cloud-agnostic)
    responses.py      # InternalResponse (cloud-agnostic)

  conf/
    __init__.py       # re-export settings
    settings.py       # Settings loader (Django-style, lazy)

  resource/
    crud.py           # generazione handler CRUD
    decorator.py      # @resource
    hooks.py          # sistema hook before/after (V2+)

  runtime/
    base.py           # BaseRuntimeProvider ABC
    aws.py            # AWSProvider (API Gateway V2)
    gcp.py            # GCPProvider (Cloud Functions HTTP)
    azure.py          # AzureProvider (Azure Functions)
    local.py          # LocalProvider (dev/test)

  agent/              # V2
    decorator.py      # @agent
    runner.py         # loop agente (LLM + tool calls)
    prompt.py         # generazione system prompt da schema
    history.py        # backend per conversation history

  mcp/                # V3
    server.py         # MCP Lambda handler
    tools.py          # generazione tool schema da modelli
    transport.py      # Streamable HTTP transport

  providers/          # V2
    base.py           # BaseProvider
    openai.py
    anthropic.py
    bedrock.py

  embeddings/         # V3
    base.py           # BaseEmbeddingProvider ABC
    openai.py         # OpenAIEmbeddingProvider
    bedrock.py        # BedrockEmbeddingProvider

  vector/             # V3
    base.py           # BaseVectorBackend ABC
    sqlite.py         # SQLiteVectorBackend (brute-force cosine, dev)
    pgvector.py       # PgVectorBackend (pgvector extension, prod)

  persistence/
    base.py           # BaseBackend ABC
    sql.py            # SQLAlchemy Core backend
    schema.py         # generazione Table da Model

  cli/
    main.py           # ragin start / dev / build
    scaffold.py       # project scaffolding (ragin start)
    dev_server.py     # Werkzeug WSGI dev server
    builder.py        # ragin build
```

### Struttura Progetto Utente (generata da `ragin start`)

```
myproject/
├── main.py              # ServerlessApp + import modelli
├── settings.py          # DATABASE_URL, EMBEDDING_PROVIDER, ecc.
└── models/
    └── __init__.py      # crea i tuoi modelli qui
```

### Settings (Django-style)

`settings.py` è un modulo Python. Tutte le variabili UPPER_CASE sono caricate come
configurazione del framework. Override possibile via env var con prefisso `RAGIN_`.

```python
# settings.py
DATABASE_URL = "sqlite:///./ragin_dev.db"
PROVIDER = "local"       # local | aws | gcp | azure
DEBUG = True
HOST = "127.0.0.1"
PORT = 8000

# V3 — Semantic Layer
EMBEDDING_PROVIDER = "openai"    # openai | bedrock | none
EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_BACKEND = "auto"          # auto | sqlite | pgvector
```

Precedenza (highest wins):
1. Env var `RAGIN_DATABASE_URL` ecc.
2. `settings.py`
3. Default built-in

---

## 12. Roadmap

### V1 — Core ✅
- [x] Model + Field (Pydantic v2, json_schema_extra)
- [x] `@resource` con CRUD automatico (5 operazioni)
- [x] Cloud-agnostic runtime provider layer (AWS, GCP, Azure, Local)
- [x] SQL backend (SQLAlchemy Core — SQLite dev, PostgreSQL prod)
- [x] `ragin build --provider aws|gcp|azure` + `ragin dev`
- [x] `ragin start` — scaffolding progetto (main.py + settings.py + models/)
- [x] `settings.py` Django-style con lazy loading e env var override
- [x] Error handling: 400 validation, 404 not found, 409 conflict (duplicate PK), 500 internal
- [x] Custom endpoints (`@app.get`, `@User.get`)
- [x] Selective operations (`operations=["create", "list", "retrieve"]`)

### V2 — Agent + MCP ✅
- [x] `@agent` decorator
- [x] MCP server (JSON-RPC: initialize, tools/list, tools/call)
- [x] Provider: OpenAI, Anthropic, Bedrock
- [x] System prompt auto-generato
- [x] Tool binding CRUD → MCP
- [x] Tool custom su agente (`@MyAgent.tool`)
- [x] Multi-model agent (`model=[User, Task]`)

### V3 — Semantic Layer
- [ ] `Field(embedding=True)` — marca i campi per embedding automatico
- [ ] `EmbeddingProvider` — astrazione per generare embeddings (OpenAI, Bedrock)
- [ ] `VectorBackend` — astrazione per vector store (SQLite brute-force dev, pgvector prod)
- [ ] Pipeline auto: insert/update → genera embedding → salva in vector store
- [ ] Tool auto-generati: `semantic_search_{resource}(query, limit)`
- [ ] Endpoint REST: `POST /{resource}/search` per semantic search diretta
- [ ] Cross-table reasoning: agent con CRUD + semantic tools su più modelli

### V4 — Advanced
- [ ] Streaming LLM response
- [ ] Conversation history persistente
- [ ] Hooks before/after
- [ ] Auth/permissions
- [ ] Step Functions / orchestrazione async per task complessi
- [ ] `ragin deploy` (IaC automatico)

---

## 13. Non-Goals (fino a V3)

- Complex SQL join automatici
- Auth avanzata built-in
- Migrations automatiche
- Deploy automatico (produce solo i file, il deploy è manuale)
- Streaming LLM response (V4)
- Step Functions / orchestrazione async (V4)
- FAISS o vector DB separati (pgvector è sufficiente per prod)
