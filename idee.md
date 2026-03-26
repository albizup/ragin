# ragin — Model-First Serverless Framework with AI Agents

## Vision

MyFW è un framework Python **model-first** e **serverless-first** che permette di:

- definire modelli una sola volta
- generare automaticamente:
  - schema database
  - API CRUD
  - validazione
  - routing HTTP
- deployare gli endpoint come **Lambda serverless (o altri provider in futuro)**

L’obiettivo è unire:
- la produttività di Django (model → tutto)
- la leggerezza delle API moderne
- la scalabilità del serverless

---

## Core Principles

### 1. Model as Single Source of Truth
Il modello definisce tutto:
- struttura dati
- schema DB
- API
- validazione

### 2. Serverless First
Non esiste un server HTTP tradizionale.  
L’app gira direttamente su:
- AWS Lambda + API Gateway (V1)

### 3. Automatic by Default, Explicit When Needed
- CRUD automatico
- override facile
- endpoint custom supportati

### 4. Cloud-Agnostic (Future)
Il core non dipende da AWS.  
Provider diversi saranno plugin:
- AWS Lambda
- GCP Cloud Run
- Azure Functions

---

## Quick Example

```python
from myfw import ServerlessApp, Model, Field, resource
from uuid import UUID

app = ServerlessApp()

@resource(
    name="players",
    operations=["create", "list", "retrieve"]
)
class Player(Model):
    id: UUID = Field(primary_key=True)
    name: str
    age: int

app.register(Player)

@app.get("/health")
def health(request):
    return {"ok": True}

@Player.get("/{id}/stats")
def player_stats(request, id):
    return {"player_id": id}
What Gets Generated Automatically

From:

app.register(Player)

The framework generates:

Database
Table: players
Columns:
id (UUID, PK)
name (string)
age (int)
API Endpoints
Method	Endpoint	Description
POST	/players	Create player
GET	/players	List players
GET	/players/{id}	Retrieve player
GET	/players/{id}/stats	Custom endpoint
GET	/health	Custom endpoint
Runtime Architecture
API Gateway
    ↓
Lambda (single handler)
    ↓
app.handle(event, context)
    ↓
Internal Router
    ↓
Generated or Custom Handler
    ↓
Database
Lambda Handler
def lambda_handler(event, context):
    return app.handle(event, context)
Internal Flow
event (API Gateway)
    ↓
InternalRequest
    ↓
Router
    ↓
Handler (auto-generated or custom)
    ↓
InternalResponse
    ↓
Lambda response
Model Definition
class Player(Model):
    id: UUID = Field(primary_key=True)
    name: str
    age: int
Field Options
Field(
    primary_key=False,
    nullable=True,
    default=None,
    unique=False,
    index=False
)
Resource Configuration
@resource(
    name="players",
    operations=["create", "list", "retrieve", "update", "delete"]
)
Supported Operations
create → POST /resource
list → GET /resource
retrieve → GET /resource/{id}
update → PATCH/PUT /resource/{id}
delete → DELETE /resource/{id}

Shortcut:

operations=["crud"]
Custom Endpoints
Global
@app.get("/health")
def health(request):
    return {"ok": True}
Resource-specific
@Player.get("/{id}/stats")
def player_stats(request, id):
    ...
Hooks (Future)
@hook(Player, "before_create")
def validate(data):
    ...
Serverless Deployment
Step 1 — Build
myfw build

Output:

Lambda package
routes.json
openapi.json
Step 2 — Export Routes
myfw export-routes > build/routes.json

Example:

{
  "lambda_handler": "main.lambda_handler",
  "routes": [
    {"method": "GET", "path": "/health"},
    {"method": "POST", "path": "/players"},
    {"method": "GET", "path": "/players"},
    {"method": "GET", "path": "/players/{id}"},
    {"method": "GET", "path": "/players/{id}/stats"}
  ]
}
Step 3 — Terraform

Terraform uses the generated routes:

route_key = "GET /players"
route_key = "POST /players"
route_key = "GET /players/{id}"

All routes point to a single Lambda.

Architecture (V1)
1 Lambda
1 API Gateway
N routes
1 database (SQL)
Internal Components
Core
ServerlessApp
Model
Field
ResourceDefinition
RouteDefinition
Persistence
SQL backend (SQLAlchemy-like)
Runtime
InternalRequest
InternalResponse
Router
Providers (future)
AWS adapter
GCP adapter
Azure adapter
Project Structure (Proposed)
myfw/
  core/
    app.py
    models.py
    fields.py
    routing.py
    requests.py
    responses.py
    registry.py

  persistence/
    base.py
    sql_backend.py

  providers/
    aws/
      adapter.py
      deploy.py

  cli/
    main.py
Design Goals
Minimal boilerplate
Strong conventions
Easy override
Clean separation:
model
API
runtime
deployment
Non-Goals (V1)
complex joins automatici
multi-cloud subito
auth avanzata
migrations avanzate
async distribuito
Future Features
multi-cloud deploy (AWS, GCP, Azure)
auth/permissions system
migrations engine
OpenAPI auto
GraphQL layer
plugin system
event-driven hooks (SQS, Pub/Sub)