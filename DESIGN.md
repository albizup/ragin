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
from uuid import UUID

app = ServerlessApp()


@resource(operations=["crud"])
class Player(Model):
    id: UUID = Field(primary_key=True)
    name: str
    age: int
    team: str


@agent(
    model=Player,
    provider=OpenAIProvider(model="gpt-4o"),
    description="Manages player records. Can create, list, retrieve, update and delete players.",
)
class PlayerAgent:
    pass


app.register(Player)
app.register_agent(PlayerAgent)
```

Quello che viene generato automaticamente:

| Layer         | Output                                                        |
|---------------|---------------------------------------------------------------|
| Database      | Tabella `players` con colonne tipizzate                       |
| CRUD API      | `POST/GET /players`, `GET/PATCH/DELETE /players/{id}`         |
| MCP Server    | Lambda MCP con tool `create_player`, `list_players`, ecc.    |
| Agent         | Lambda agent su `POST /players/agent`                         |
| System Prompt | Generato dallo schema del modello + `description`            |
| OpenAPI       | `openapi.json` completo                                       |

---

## 4. Architettura

### 4.1 Vista ad alto livello

```
Client
  │
  ▼
API Gateway
  ├── /players          →  CRUD Lambda
  ├── /players/{id}     →  CRUD Lambda
  ├── /players/agent    →  Agent Lambda
  └── /mcp              →  MCP Lambda
```

Ogni blocco è una Lambda indipendente. Non c'è un server condiviso.

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
class Player(Model):
    id: UUID = Field(primary_key=True)
    name: str
    age: int
    team: str = Field(nullable=True, index=True)
```

### Field Options

```python
Field(
    primary_key=False,
    nullable=True,
    default=None,
    unique=False,
    index=False,
    description="",   # usato nel system prompt dell'agente
)
```

---

## 6. Resource Layer

### Decorator

```python
@resource(
    name="players",                                           # default: plurale del nome classe
    operations=["create", "list", "retrieve", "update", "delete"],  # oppure: ["crud"]
    path_prefix="/v1",                                        # opzionale
)
class Player(Model):
    ...
```

### Operazioni generate

| Operation  | Method | Path             |
|------------|--------|------------------|
| `create`   | POST   | `/players`       |
| `list`     | GET    | `/players`       |
| `retrieve` | GET    | `/players/{id}`  |
| `update`   | PATCH  | `/players/{id}`  |
| `delete`   | DELETE | `/players/{id}`  |

### Endpoint custom

```python
# globale
@app.get("/health")
def health(request):
    return {"ok": True}

# resource-specific
@Player.get("/{id}/stats")
def player_stats(request, id: UUID):
    return {"player_id": id, "goals": ...}
```

### Hooks

```python
@hook(Player, "before_create")
def validate_age(data: Player) -> Player:
    if data.age < 16:
        raise ValidationError("Player too young")
    return data
```

---

## 7. Agent Layer

### Decorator

```python
@agent(
    model=Player,                        # modello di riferimento (o lista di modelli)
    provider=OpenAIProvider(...),        # LLM provider
    description="...",                   # aggiunto al system prompt
    tools=["crud"],                      # tool abilitati: "crud", lista operazioni, o custom
    history_backend=None,                # None = stateless, "dynamodb" = history persistente
)
class PlayerAgent:
    pass
```

L'agente genera automaticamente:
- **system prompt** dal nome del modello, campi, descrizioni dei Field e `description`
- **tool schema** MCP per ogni operazione abilitata
- **endpoint** `POST /players/agent`

### Request/Response

```python
# Request
POST /players/agent
{
  "message": "Crea un giocatore di nome Marco, 22 anni, team Juventus",
  "thread_id": "abc123"    // opzionale, per history
}

# Response
{
  "message": "Ho creato il giocatore Marco con successo.",
  "tool_calls": [...],     // opzionale, per debug
  "thread_id": "abc123"
}
```

### Tool custom per l'agente

```python
@PlayerAgent.tool
def player_ranking(age_min: int, limit: int = 10) -> list[dict]:
    """Ritorna i migliori giocatori per fascia d'età."""
    ...
```

Il tool viene aggiunto automaticamente al MCP server e reso disponibile all'agente.

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
list_players(filters: dict, limit: int, offset: int) → list[Player]
get_player(id: UUID) → Player
update_player(id: UUID, data: dict) → Player
delete_player(id: UUID) → bool
```

Il JSON schema di ogni tool è derivato dal modello Pydantic (stessa definizione usata
per la validazione CRUD).

### Flusso interno MCP

```
Agent Lambda
  │  HTTP POST /mcp/tools/call  {"name": "list_players", "arguments": {...}}
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
ragin build           # pacchetto Lambda, routes.json, openapi.json, mcp-manifest.json
ragin export-routes   # stampa routes.json su stdout
ragin deploy          # deploy su AWS (CDK under the hood)
ragin dev             # server locale per sviluppo
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
    "agent": { "handler": "main.agent_handler",  "routes": [{"method": "POST", "path": "/players/agent"}] },
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

## 11. Struttura del Progetto

```
ragin/
  core/
    app.py            # ServerlessApp
    models.py         # Model base class
    fields.py         # Field
    routing.py        # RouteDefinition, Router
    registry.py       # registro globale di modelli, agenti, tool
    requests.py       # InternalRequest
    responses.py      # InternalResponse

  resource/
    crud.py           # generazione handler CRUD
    hooks.py          # sistema hook before/after

  agent/
    decorator.py      # @agent
    runner.py         # loop agente (LLM + tool calls)
    prompt.py         # generazione system prompt da schema
    history.py        # backend per conversation history

  mcp/
    server.py         # MCP Lambda handler
    tools.py          # generazione tool schema da modelli
    transport.py      # Streamable HTTP transport

  providers/
    base.py           # BaseProvider
    openai.py
    anthropic.py
    bedrock.py
    langchain.py
    pydantic_ai.py

  persistence/
    base.py
    sql.py            # SQLAlchemy backend
    dynamodb.py       # DynamoDB backend (futuro)

  cli/
    main.py           # ragin build / deploy / dev

  deploy/
    aws_cdk.py        # CDK stack generata
    terraform.py      # Terraform output (futuro)
```

---

## 12. Roadmap

### V1 — Core
- [ ] Model + Field
- [ ] `@resource` con CRUD automatico
- [ ] Single CRUD Lambda handler
- [ ] SQL backend (SQLite dev, PostgreSQL prod)
- [ ] `ragin build` + `ragin dev`
- [ ] AWS CDK deploy

### V2 — Agent + MCP
- [ ] `@agent` decorator
- [ ] MCP Lambda serverless
- [ ] Provider: OpenAI, Anthropic, Bedrock
- [ ] System prompt auto-generato
- [ ] Tool binding CRUD → MCP
- [ ] Tool custom su agente

### V3 — Advanced
- [ ] Provider: LangChain, PydanticAI
- [ ] Conversation history (DynamoDB)
- [ ] Hooks before/after
- [ ] Multi-model agent
- [ ] Auth/permissions
- [ ] Migration engine
- [ ] Multi-cloud (GCP Cloud Run, Azure Functions)

---

## 13. Non-Goals (V1)

- Complex SQL join automatici
- Multi-cloud immediato
- Auth avanzata built-in
- Migrations automatiche
- Streaming LLM response (V3)
