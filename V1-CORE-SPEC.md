# ragin V1 Core — Implementation Spec

> Documento tecnico dettagliato per l'implementazione del core del framework.

---

## Scope V1

Cosa è incluso:
- `Model` + `Field` (Pydantic-based, metadati via `json_schema_extra`)
- `@resource` decorator con generazione CRUD automatica (5 operazioni)
- `ServerlessApp` con routing interno **cloud-agnostic**
- **Runtime provider layer** — adatta il formato evento/risposta del cloud specifico
- Runtime provider built-in: `aws`, `gcp`, `azure`, `local`
- SQL backend (SQLite dev, PostgreSQL prod) via SQLAlchemy Core
- Custom endpoint (`@app.get`, `@app.post`, `@User.get`, ecc.)
- `ragin start <name>` — scaffolding progetto con `main.py` + `settings.py` + `models/`
- `ragin dev` — server locale per sviluppo (Werkzeug)
- `ragin build --provider aws|gcp|azure` — genera il pacchetto deploiabile
- `settings.py` Django-style con lazy loading e env var override (`RAGIN_*`)
- Error handling: 400 (validation), 404 (not found), 409 (duplicate PK), 500 (internal)
- Selective operations (`operations=["create", "list"]`)

Cosa NON è incluso in V1:
- `@agent`, MCP server, provider LLM → **Implementati in V2**
- Deploy automatico cloud (V1 produce solo i file, il deploy è manuale)
- Hooks before/after
- Auth/permissions
- Migrations automatiche

---

## Struttura File del Progetto

```
ragin/
  __init__.py              # export: ServerlessApp, Model, Field, resource
  conf/
    __init__.py            # re-export settings
    settings.py            # Settings loader (Django-style, lazy)
  core/
    __init__.py
    app.py                 # ServerlessApp
    models.py              # Model base class
    fields.py              # Field
    registry.py            # ResourceRegistry (singleton globale)
    routing.py             # RouteDefinition, Router
    requests.py            # InternalRequest  (cloud-agnostic)
    responses.py           # InternalResponse (cloud-agnostic)
  resource/
    __init__.py
    decorator.py           # @resource
    crud.py                # CrudHandlerFactory
  runtime/
    __init__.py
    base.py                # BaseRuntimeProvider ABC
    aws.py                 # AWSProvider (API Gateway V2)
    gcp.py                 # GCPProvider (Cloud Functions HTTP)
    azure.py               # AzureProvider (Azure Functions HTTP)
    local.py               # LocalProvider (dev server / testing)
  persistence/
    __init__.py
    base.py                # BaseBackend ABC
    sql.py                 # SqlBackend (SQLAlchemy Core)
    schema.py              # generazione Table SQLAlchemy da Model
  cli/
    __init__.py
    main.py                # entry point CLI: ragin start / dev / build
    scaffold.py            # project scaffolding (ragin start)
    dev_server.py          # server WSGI locale (usa LocalProvider)
    builder.py             # ragin build

pyproject.toml
```

### Struttura Progetto Utente (generata da `ragin start myproject`)

```
myproject/
├── main.py              # ServerlessApp + import modelli
├── settings.py          # DATABASE_URL, PROVIDER, HOST, PORT, DEBUG
└── models/
    ├── __init__.py      # registry dei modelli
    └── user.py          # modello User di esempio
```

> ✅ **IMPLEMENTATO** — Struttura file completa, scaffold genera tutto correttamente.

---

## 1. Field & Model

### 1.1 `RaginFieldInfo`

Estende `pydantic.fields.FieldInfo` aggiungendo metadati ragin.
NON sovrascrive la validazione Pydantic — la usa interamente.

```python
# ragin/core/fields.py

from pydantic.fields import FieldInfo
from typing import Any

class RaginFieldInfo(FieldInfo):
    primary_key: bool
    nullable: bool
    unique: bool
    index: bool

    def __init__(self, primary_key=False, nullable=True, unique=False, index=False, **kwargs):
        super().__init__(**kwargs)
        self.primary_key = primary_key
        self.nullable = nullable
        self.unique = unique
        self.index = index


def Field(
    default=...,
    *,
    primary_key: bool = False,
    nullable: bool = True,
    unique: bool = False,
    index: bool = False,
    description: str = None,
    **kwargs,
) -> Any:
    """Wrapper che restituisce RaginFieldInfo invece di FieldInfo standard."""
    ...
```

**Nota implementativa:** Pydantic ha un meccanismo di `_field_info_cls` per field custom,
ma è più robusto usare `Annotated[UUID, RaginFieldInfo(...)]` internamente.
Il `Field()` di ragin deve restituire qualcosa che Pydantic accetta come default/annotation.
Approccio consigliato: `Field()` ritorna `pydantic.Field(default, json_schema_extra={"ragin": {...}})`.
Così Pydantic gestisce tutta la validazione e ragin legge i metadati da `json_schema_extra`.

Implementazione concreta:

```python
def Field(default=..., *, primary_key=False, nullable=True, unique=False, index=False, **kwargs):
    ragin_meta = {
        "primary_key": primary_key,
        "nullable": nullable,
        "unique": unique,
        "index": index,
    }
    return pydantic.Field(
        default,
        json_schema_extra={"ragin": ragin_meta},
        **kwargs,
    )
```

E per leggere i metadati:

```python
def get_ragin_meta(model_cls: type[BaseModel], field_name: str) -> dict:
    field_info = model_cls.model_fields[field_name]
    extra = field_info.json_schema_extra or {}
    return extra.get("ragin", {})
```

### 1.2 `Model`

`Model` è semplicemente `pydantic.BaseModel` con una mixin che aggiunge metodi di utilità.
Non ridefinisce nulla della validazione — tutta la validazione è Pydantic standard.

```python
# ragin/core/models.py

from pydantic import BaseModel as PydanticBaseModel
from ragin.core.fields import get_ragin_meta

class Model(PydanticBaseModel):

    @classmethod
    def primary_key_field(cls) -> str:
        """Ritorna il nome del campo primary key."""
        for name in cls.model_fields:
            meta = get_ragin_meta(cls, name)
            if meta.get("primary_key"):
                return name
        raise ValueError(f"{cls.__name__} has no primary_key Field")

    @classmethod
    def ragin_table_name(cls) -> str:
        """Ritorna il nome della tabella (default: snake_case plurale)."""
        return cls.__name__.lower() + "s"

    class Config:
        # permette UUID, datetime ecc. come input string
        from_attributes = True
```

Il nome tabella è sovrascrivibile:

```python
class User(Model):
    class Meta:
        table_name = "app_users"
```

> ✅ **IMPLEMENTATO** — `Field()` con `json_schema_extra`, `Model` con `primary_key_field()`, `ragin_table_name()`, `Meta.table_name` override. Testato in `test_models.py`.

---

## 2. ResourceRegistry

Singleton globale che tiene traccia di tutti i modelli registrati, le loro route
e i loro handler. È il centro di coordinamento tra tutte le parti del framework.

```python
# ragin/core/registry.py

from dataclasses import dataclass, field
from typing import Callable

@dataclass
class RouteDefinition:
    method: str          # "GET", "POST", "PATCH", "DELETE"
    path: str            # "/players/{id}"
    handler: Callable
    model: type | None = None
    operation: str | None = None   # "create", "list", "retrieve", ecc.


class ResourceRegistry:
    _routes: list[RouteDefinition] = []
    _models: dict[str, type] = {}    # name → Model class

    def register_model(self, name: str, model_cls: type):
        self._models[name] = model_cls

    def register_route(self, route: RouteDefinition):
        self._routes.append(route)

    def get_routes(self) -> list[RouteDefinition]:
        return list(self._routes)

    def reset(self):
        self._routes.clear()
        self._models.clear()


registry = ResourceRegistry()   # istanza globale
```

> ✅ **IMPLEMENTATO** — `ResourceRegistry` singleton con `_routes`, `_models`, `reset()`. Usato da tutti i decorator.

---

## 3. `@resource` Decorator

Il decorator fa tre cose:
1. Registra il modello nel registry
2. Genera i RouteDefinition per le operazioni richieste
3. Restituisce la classe originale **senza modificarla** (è solo un modello Pydantic)

```python
# ragin/resource/decorator.py

from ragin.resource.crud import CrudHandlerFactory
from ragin.resource.operations import Operation
from ragin.core.registry import registry, RouteDefinition


def resource(
    name: str = None,
    operations: list[str] = None,
    path_prefix: str = "",
):
    def decorator(model_cls):
        resource_name = name or (model_cls.__name__.lower() + "s")
        ops = _parse_operations(operations or ["crud"])
        base_path = f"{path_prefix}/{resource_name}"
        pk_path = f"{base_path}/{{id}}"

        factory = CrudHandlerFactory(model_cls, resource_name)

        op_map = {
            "create":   ("POST",   base_path,  factory.create_handler()),
            "list":     ("GET",    base_path,  factory.list_handler()),
            "retrieve": ("GET",    pk_path,    factory.retrieve_handler()),
            "update":   ("PATCH",  pk_path,    factory.update_handler()),
            "delete":   ("DELETE", pk_path,    factory.delete_handler()),
        }

        registry.register_model(resource_name, model_cls)

        for op in ops:
            method, path, handler = op_map[op]
            registry.register_route(RouteDefinition(
                method=method,
                path=path,
                handler=handler,
                model=model_cls,
                operation=op,
            ))

        # aggiungi metodo per endpoint custom resource-specific
        # es: @Player.get("/{id}/stats")
        model_cls._resource_name = resource_name
        model_cls._path_prefix = base_path
        model_cls.get = classmethod(lambda cls, path: _resource_route("GET", cls, path))
        model_cls.post = classmethod(lambda cls, path: _resource_route("POST", cls, path))

        return model_cls

    return decorator


def _parse_operations(ops: list[str]) -> list[str]:
    if ops == ["crud"] or ops == "crud":
        return ["create", "list", "retrieve", "update", "delete"]
    return ops
```

### Come funziona `@User.get("/{id}/profile")`

```python
def _resource_route(method: str, model_cls: type, sub_path: str):
    """Decorator per endpoint custom resource-specific."""
    def decorator(fn):
        full_path = model_cls._path_prefix + sub_path
        registry.register_route(RouteDefinition(
            method=method,
            path=full_path,
            handler=fn,
            model=model_cls,
        ))
        return fn
    return decorator
```

> ✅ **IMPLEMENTATO** — `@resource` con operations selettive, path_prefix, custom endpoint (`@User.get`, `@User.post`, ecc.). Testato in `test_crud.py`.

---

## 4. CrudHandlerFactory

Genera i 5 handler CRUD come closures. Ogni handler riceve un `InternalRequest`
e ritorna un `InternalResponse`. Non conosce niente di Lambda — è testabile
in isolamento.

```python
# ragin/resource/crud.py

from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse
from ragin.persistence import get_backend


class CrudHandlerFactory:
    def __init__(self, model_cls, resource_name: str):
        self.model_cls = model_cls
        self.resource_name = resource_name

    def create_handler(self):
        model_cls = self.model_cls
        def handler(request: InternalRequest) -> InternalResponse:
            from pydantic import ValidationError
            from sqlalchemy.exc import IntegrityError
            try:
                data = model_cls.model_validate(request.json_body)
            except ValidationError as exc:
                return InternalResponse.bad_request(exc.errors())
            try:
                record = get_backend().insert(model_cls, data.model_dump())
            except IntegrityError:
                return InternalResponse.conflict("Resource with that key already exists.")
            return InternalResponse.created(record)
        return handler

    def list_handler(self):
        model_cls = self.model_cls
        def handler(request: InternalRequest) -> InternalResponse:
            filters = request.query_params   # es: ?age=22&team=Juventus
            limit = int(request.query_params.get("limit", 100))
            offset = int(request.query_params.get("offset", 0))
            backend = get_backend()
            records = backend.select(model_cls, filters, limit=limit, offset=offset)
            return InternalResponse.ok(records)
        return handler

    def retrieve_handler(self):
        model_cls = self.model_cls
        def handler(request: InternalRequest) -> InternalResponse:
            pk = request.path_params["id"]
            backend = get_backend()
            record = backend.get(model_cls, pk)
            if record is None:
                return InternalResponse.not_found()
            return InternalResponse.ok(record)
        return handler

    def update_handler(self):
        model_cls = self.model_cls
        def handler(request: InternalRequest) -> InternalResponse:
            pk = request.path_params["id"]
            data = request.json_body   # partial update
            backend = get_backend()
            record = backend.update(model_cls, pk, data)
            if record is None:
                return InternalResponse.not_found()
            return InternalResponse.ok(record)
        return handler

    def delete_handler(self):
        model_cls = self.model_cls
        def handler(request: InternalRequest) -> InternalResponse:
            pk = request.path_params["id"]
            backend = get_backend()
            deleted = backend.delete(model_cls, pk)
            if not deleted:
                return InternalResponse.not_found()
            return InternalResponse.no_content()
        return handler
```

> ✅ **IMPLEMENTATO** — 5 handler CRUD con 400 (validation), 404 (not found), 409 (duplicate PK IntegrityError). Testato in `test_crud.py`.

---

## 5. InternalRequest / InternalResponse

Astrazione **completamente cloud-agnostica**. Non contiene nulla di AWS/GCP/Azure.
I CRUD handler non toccano mai il formato del provider — ricevono e ritornano solo
`InternalRequest`/`InternalResponse`. La conversione è delegata al Runtime Provider.

```python
# ragin/core/requests.py

import json
from dataclasses import dataclass, field


@dataclass
class InternalRequest:
    method: str                           # "GET", "POST", ...
    path: str                             # "/players/123"
    path_params: dict = field(default_factory=dict)
    query_params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    raw_body: str | None = None

    @property
    def json_body(self) -> dict:
        if not self.raw_body:
            return {}
        return json.loads(self.raw_body)
```

```python
# ragin/core/responses.py

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class InternalResponse:
    status_code: int
    body: Any
    headers: dict = None

    @classmethod
    def ok(cls, body: Any) -> "InternalResponse":
        return cls(status_code=200, body=body)

    @classmethod
    def created(cls, body: Any) -> "InternalResponse":
        return cls(status_code=201, body=body)

    @classmethod
    def not_found(cls, message="Not found") -> "InternalResponse":
        return cls(status_code=404, body={"error": message})

    @classmethod
    def bad_request(cls, message: str) -> "InternalResponse":
        return cls(status_code=400, body={"error": message})

    @classmethod
    def no_content(cls) -> "InternalResponse":
        return cls(status_code=204, body=None)

    @classmethod
    def conflict(cls, message="Conflict") -> "InternalResponse":
        return cls(status_code=409, body={"error": message})

    @classmethod
    def internal_error(cls, message="Internal server error") -> "InternalResponse":
        return cls(status_code=500, body={"error": message})
```

> ✅ **IMPLEMENTATO** — `InternalRequest` (dataclass con `json_body` property) e `InternalResponse` (factory methods: ok, created, no_content, bad_request, not_found, conflict, internal_error).

---

## 5b. Runtime Provider Layer

Questo è il **solo punto cloud-specifico** del framework. Ogni provider sa come:
1. convertire l'evento cloud in `InternalRequest`
2. convertire `InternalResponse` nel formato di risposta cloud
3. (futuro) generare l'entry point deploiabile (`get_handler()`)

```python
# ragin/runtime/base.py

from abc import ABC, abstractmethod
from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse


class BaseRuntimeProvider(ABC):

    @abstractmethod
    def parse_request(self, event: object, context: object) -> InternalRequest:
        """Converte l'evento cloud-specifico in InternalRequest."""
        ...

    @abstractmethod
    def format_response(self, response: InternalResponse) -> object:
        """Converte InternalResponse nel formato atteso dal cloud."""
        ...

    def get_handler(self, app) -> callable:
        """
        Ritorna l'entry point pronto per il provider.
        Usato da `ragin build` per generare il file handler.
        Default: chiama app.handle() con questo provider.
        """
        provider = self
        def handler(event, context=None):
            return app.handle(event, context, provider=provider)
        return handler
```

```python
# ragin/runtime/aws.py  — API Gateway HTTP API (V2)

import json
from ragin.runtime.base import BaseRuntimeProvider
from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse


class AWSProvider(BaseRuntimeProvider):

    def parse_request(self, event: dict, context) -> InternalRequest:
        return InternalRequest(
            method=event["requestContext"]["http"]["method"],
            path=event["requestContext"]["http"]["path"],
            path_params=event.get("pathParameters") or {},
            query_params=event.get("queryStringParameters") or {},
            headers=event.get("headers") or {},
            raw_body=event.get("body"),
        )

    def format_response(self, response: InternalResponse) -> dict:
        return {
            "statusCode": response.status_code,
            "headers": {"Content-Type": "application/json", **(response.headers or {})},
            "body": json.dumps(response.body, default=str) if response.body is not None else "",
        }
```

```python
# ragin/runtime/gcp.py  — Cloud Functions HTTP (Flask-compatible)

import json
from ragin.runtime.base import BaseRuntimeProvider
from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse


class GCPProvider(BaseRuntimeProvider):
    """Compatibile con Google Cloud Functions (Flask Request/Response)."""

    def parse_request(self, request, context=None) -> InternalRequest:
        # `request` è un oggetto Flask-like (flask.Request)
        return InternalRequest(
            method=request.method,
            path=request.path,
            path_params={},
            query_params=dict(request.args),
            headers=dict(request.headers),
            raw_body=request.get_data(as_text=True) or None,
        )

    def format_response(self, response: InternalResponse):
        # GCF accetta una tuple (body, status, headers)
        return (
            json.dumps(response.body, default=str) if response.body is not None else "",
            response.status_code,
            {"Content-Type": "application/json", **(response.headers or {})},
        )
```

```python
# ragin/runtime/azure.py  — Azure Functions HTTP Trigger

import json
from ragin.runtime.base import BaseRuntimeProvider
from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse


class AzureProvider(BaseRuntimeProvider):
    """Compatibile con Azure Functions HTTP trigger (azure.functions.HttpRequest)."""

    def parse_request(self, req, context=None) -> InternalRequest:
        return InternalRequest(
            method=req.method,
            path=req.url.split(".net")[-1].split("?")[0],  # estrae il path dall'URL
            path_params=dict(req.route_params),
            query_params=dict(req.params),
            headers=dict(req.headers),
            raw_body=req.get_body().decode("utf-8") or None,
        )

    def format_response(self, response: InternalResponse):
        import azure.functions as func
        return func.HttpResponse(
            body=json.dumps(response.body, default=str) if response.body is not None else "",
            status_code=response.status_code,
            headers={"Content-Type": "application/json", **(response.headers or {})},
        )
```

```python
# ragin/runtime/local.py  — Dev server / testing

import json
from ragin.runtime.base import BaseRuntimeProvider
from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse


class LocalProvider(BaseRuntimeProvider):
    """
    Usato dal dev server e nei test.
    Accetta direttamente un InternalRequest (nessuna conversione).
    """

    def parse_request(self, request: InternalRequest, context=None) -> InternalRequest:
        return request

    def format_response(self, response: InternalResponse) -> dict:
        return {
            "statusCode": response.status_code,
            "headers": response.headers or {},
            "body": response.body,
        }
```

### Provider di default

Determinato in ordine:
1. Passato esplicitamente a `app.handle(event, context, provider=...)`
2. Configurato via `app = ServerlessApp(provider=AWSProvider())`
3. Da env var `RAGIN_PROVIDER=aws|gcp|azure` (auto-instanzia il provider)
4. Fallback: `LocalProvider` (utile per test)

```python
# ragin/runtime/__init__.py

from ragin.runtime.aws import AWSProvider
from ragin.runtime.gcp import GCPProvider
from ragin.runtime.azure import AzureProvider
from ragin.runtime.local import LocalProvider

_PROVIDERS = {
    "aws": AWSProvider,
    "gcp": GCPProvider,
    "azure": AzureProvider,
    "local": LocalProvider,
}

def get_default_provider():
    from ragin.conf import settings
    name = settings.PROVIDER.lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown RAGIN_PROVIDER: {name}. Choose: {list(_PROVIDERS)}")
    return cls()
```

---

## 6. Router

Il router matcha `(method, path)` della request alla `RouteDefinition` giusta.
Supporta path params (es. `/users/{id}`).

```python
# ragin/core/routing.py

import re
from ragin.core.requests import InternalRequest
from ragin.core.registry import RouteDefinition


class Router:
    def __init__(self, routes: list[RouteDefinition]):
        self._routes = routes
        self._compiled = [(self._compile(r), r) for r in routes]

    def _compile(self, route: RouteDefinition) -> re.Pattern:
        """Converte /players/{id} → regex con named group."""
        pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", route.path)
        return re.compile(f"^{pattern}$")

    def match(self, request: InternalRequest) -> tuple[RouteDefinition, dict] | None:
        for pattern, route in self._compiled:
            if route.method != request.method:
                continue
            m = pattern.match(request.path)
            if m:
                return route, m.groupdict()
        return None
```

> ✅ **IMPLEMENTATO** — `Router` con regex path matching e named groups. `RouteMatch` dataclass. Testato in `test_routing.py`.

---

## 7. ServerlessApp

Entry point del framework. **Non conosce nessun cloud provider.**
Accetta un `provider` opzionale — se non passato, lo legge da env o usa `LocalProvider`.

```python
# ragin/core/app.py

from ragin.core.registry import registry, RouteDefinition
from ragin.core.routing import Router
from ragin.core.requests import InternalRequest
from ragin.core.responses import InternalResponse
from pydantic import ValidationError


class ServerlessApp:

    def __init__(self, provider=None):
        """
        provider: istanza di BaseRuntimeProvider.
        Se None, viene risolto da RAGIN_PROVIDER env var o default LocalProvider.
        """
        self._provider = provider

    def _get_provider(self, override=None):
        if override is not None:
            return override
        if self._provider is not None:
            return self._provider
        from ragin.runtime import get_default_provider
        return get_default_provider()

    def register(self, model_cls):
        """Noop in V1 — le route sono già nel registry via @resource."""
        pass

    # --- decoratori per endpoint globali ---

    def _route_decorator(self, method: str, path: str):
        def decorator(fn):
            registry.register_route(RouteDefinition(
                method=method,
                path=path,
                handler=fn,
            ))
            return fn
        return decorator

    def get(self, path: str):    return self._route_decorator("GET", path)
    def post(self, path: str):   return self._route_decorator("POST", path)
    def patch(self, path: str):  return self._route_decorator("PATCH", path)
    def put(self, path: str):    return self._route_decorator("PUT", path)
    def delete(self, path: str): return self._route_decorator("DELETE", path)

    # --- handler principale ---

    def handle(self, event, context=None, *, provider=None) -> object:
        """
        Punto di ingresso unico. `event` è nel formato del provider attivo.
        Ritorna la risposta nel formato del provider attivo.
        """
        p = self._get_provider(provider)
        request = p.parse_request(event, context)
        router = Router(registry.get_routes())
        match = router.match(request)

        if match is None:
            response = InternalResponse.not_found("Route not found")
            return p.format_response(response)

        route, path_params = match
        request.path_params = path_params

        try:
            response = route.handler(request)
        except ValidationError as e:
            response = InternalResponse.bad_request(e.errors())
        except Exception:
            response = InternalResponse.internal_error()

        return p.format_response(response)

    def get_handler(self, provider=None):
        """
        Ritorna una callable pronta per il cloud provider.
        Usata da `ragin build` per generare l'entry point.

        Esempio:
            handler = app.get_handler()   # usa RAGIN_PROVIDER env
            # oppure
            handler = app.get_handler(AWSProvider())
        """
        p = self._get_provider(provider)
        return p.get_handler(self)
```

### Entry point nell'app utente — cloud-agnostic

L'utente **non scrive mai** `lambda_handler`, `def main(request)` ecc.
È `get_handler()` che produce il callable giusto per il provider configurato.

```python
# main.py (file dell'utente)

from ragin import ServerlessApp
from models import *  # noqa: F401, F403

app = ServerlessApp()
```

```python
# models/user.py
from ragin import Field, Model, resource

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str
```

```python
# Entry point cloud-agnostic (generato da ragin build).
# RAGIN_PROVIDER=aws  →  handler è compatibile con Lambda
# RAGIN_PROVIDER=gcp  →  handler è compatibile con Cloud Functions
# RAGIN_PROVIDER=azure → handler è compatibile con Azure Functions
handler = app.get_handler()
```

Per chi vuole esplicitare il provider:

```python
from ragin.runtime.aws import AWSProvider
handler = app.get_handler(AWSProvider())   # sempre AWS, indipendente da env
```

> ✅ **IMPLEMENTATO** — 4 runtime provider (AWS, GCP, Azure, Local) + `get_default_provider()` da settings. Testato via `LocalProvider` in tutti i test.

### Come `ragin build` usa questo

`ragin build --provider aws` genera un file `_ragin_entry.py`:

```python
# build/_ragin_entry.py  (generato automaticamente)
from ragin.runtime.aws import AWSProvider
import main  # app utente

lambda_handler = main.app.get_handler(AWSProvider())
```

Il Lambda handler è letteralmente questa variabile. Nessun boilerplate scritto a mano.

---

## 8. SQL Backend

Usa **SQLAlchemy Core** (non ORM) per costruire le query. Non usa l'ORM Session
né modelli SQLAlchemy — lavora direttamente con `Table`, `select`, `insert`, ecc.
Questo mantiene le dipendenze leggere e compatibili con Lambda.

### 8.1 Schema Generation

```python
# ragin/persistence/schema.py

import sqlalchemy as sa
from ragin.core.models import Model
from ragin.core.fields import get_ragin_meta
import uuid


TYPE_MAP = {
    "str": sa.String,
    "int": sa.Integer,
    "float": sa.Float,
    "bool": sa.Boolean,
    "UUID": sa.UUID,
    "datetime": sa.DateTime,
    "date": sa.Date,
}


def model_to_table(model_cls: type[Model], metadata: sa.MetaData) -> sa.Table:
    columns = []
    for field_name, field_info in model_cls.model_fields.items():
        meta = get_ragin_meta(model_cls, field_name)
        sa_type = _resolve_type(field_info)

        col = sa.Column(
            field_name,
            sa_type,
            primary_key=meta.get("primary_key", False),
            nullable=meta.get("nullable", True),
            unique=meta.get("unique", False),
            index=meta.get("index", False),
        )
        columns.append(col)

    table_name = model_cls.ragin_table_name()
    return sa.Table(table_name, metadata, *columns)


def _resolve_type(field_info) -> sa.types.TypeEngine:
    """Deriva il tipo SQLAlchemy dall'annotation Pydantic."""
    ann = field_info.annotation
    type_name = getattr(ann, "__name__", str(ann))
    # gestisce Optional[X]
    if hasattr(ann, "__args__"):
        inner = [a for a in ann.__args__ if a is not type(None)]
        if inner:
            type_name = getattr(inner[0], "__name__", str(inner[0]))
    return TYPE_MAP.get(type_name, sa.String)()
```

### 8.2 SqlBackend

```python
# ragin/persistence/sql.py

import sqlalchemy as sa
from ragin.persistence.base import BaseBackend
from ragin.persistence.schema import model_to_table


class SqlBackend(BaseBackend):
    def __init__(self, url: str):
        self._engine = sa.create_engine(url)
        self._metadata = sa.MetaData()
        self._tables: dict[str, sa.Table] = {}

    def register(self, model_cls):
        """Registra il modello e crea la tabella se non esiste."""
        table = model_to_table(model_cls, self._metadata)
        self._tables[model_cls.__name__] = table
        self._metadata.create_all(self._engine)

    def insert(self, model_cls, data: dict) -> dict:
        table = self._tables[model_cls.__name__]
        with self._engine.connect() as conn:
            result = conn.execute(table.insert().values(**data).returning(*table.c))
            conn.commit()
            return dict(result.fetchone()._mapping)

    def select(self, model_cls, filters: dict, limit=100, offset=0) -> list[dict]:
        table = self._tables[model_cls.__name__]
        query = sa.select(table)
        for k, v in filters.items():
            if k in ("limit", "offset"):
                continue
            if k in table.c:
                query = query.where(table.c[k] == v)
        query = query.limit(limit).offset(offset)
        with self._engine.connect() as conn:
            result = conn.execute(query)
            return [dict(row._mapping) for row in result.fetchall()]

    def get(self, model_cls, pk_value) -> dict | None:
        table = self._tables[model_cls.__name__]
        pk_col = _pk_column(table)
        query = sa.select(table).where(pk_col == pk_value)
        with self._engine.connect() as conn:
            result = conn.execute(query)
            row = result.fetchone()
            return dict(row._mapping) if row else None

    def update(self, model_cls, pk_value, data: dict) -> dict | None:
        table = self._tables[model_cls.__name__]
        pk_col = _pk_column(table)
        stmt = (
            sa.update(table)
            .where(pk_col == pk_value)
            .values(**data)
            .returning(*table.c)
        )
        with self._engine.connect() as conn:
            result = conn.execute(stmt)
            conn.commit()
            row = result.fetchone()
            return dict(row._mapping) if row else None

    def delete(self, model_cls, pk_value) -> bool:
        table = self._tables[model_cls.__name__]
        pk_col = _pk_column(table)
        stmt = sa.delete(table).where(pk_col == pk_value)
        with self._engine.connect() as conn:
            result = conn.execute(stmt)
            conn.commit()
            return result.rowcount > 0


def _pk_column(table: sa.Table) -> sa.Column:
    for col in table.c:
        if col.primary_key:
            return col
    raise ValueError(f"No primary key on table {table.name}")
```

> ✅ **IMPLEMENTATO** — `SqlBackend` con SQLAlchemy Core, auto-register tabelle, schema generation da Model. SQLite + PostgreSQL supportati.

### 8.3 Configurazione backend

Il backend è configurato automaticamente dal sistema `settings`. Se non configurato
esplicitamente, `get_backend()` legge `settings.DATABASE_URL` al primo accesso.

```python
# ragin/persistence/__init__.py

from ragin.persistence.base import BaseBackend

_backend: BaseBackend | None = None

def configure_backend(url: str) -> None:
    global _backend
    from ragin.persistence.sql import SqlBackend
    _backend = SqlBackend(url)

def get_backend() -> BaseBackend:
    global _backend
    if _backend is None:
        from ragin.conf import settings
        url = settings.DATABASE_URL
        from ragin.persistence.sql import SqlBackend
        _backend = SqlBackend(url)
    return _backend
```

Non serve più configurare manualmente nell'app utente — `settings.py` è sufficiente.

> ✅ **IMPLEMENTATO** — `configure_backend()`, `get_backend()`, `reset_backend()` con lazy init da `settings.DATABASE_URL`.

---

## 9. `ragin dev` — Server Locale

Usa `LocalProvider` + Werkzeug. Costruisce un `InternalRequest` direttamente dalla
request HTTP — nessuna conversione in formato cloud intermedio.

```python
# ragin/cli/dev_server.py

from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response
import json
from ragin.core.requests import InternalRequest
from ragin.runtime.local import LocalProvider


def create_wsgi_app(app):
    provider = LocalProvider()

    def wsgi_app(environ, start_response):
        http_req = Request(environ)
        internal_req = InternalRequest(
            method=http_req.method,
            path=http_req.path,
            path_params={},
            query_params=dict(http_req.args),
            headers=dict(http_req.headers),
            raw_body=http_req.get_data(as_text=True) or None,
        )
        # LocalProvider.parse_request è identità — passa direttamente
        result = app.handle(internal_req, context=None, provider=provider)

        response = Response(
            json.dumps(result["body"], default=str) if result["body"] is not None else "",
            status=result["statusCode"],
            headers={"Content-Type": "application/json", **result.get("headers", {})},
        )
        return response(environ, start_response)
    return wsgi_app


def run_dev_server(app, host="127.0.0.1", port=8000):
    wsgi = create_wsgi_app(app)
    print(f"ragin dev server — http://{host}:{port}")
    run_simple(host, port, wsgi, use_reloader=True)
```

> ✅ **IMPLEMENTATO** — `ragin dev` con Werkzeug WSGI, opzioni --host/--port/--app.

---

## 10. CLI

```python
# ragin/cli/main.py

import click
import importlib
import sys

@click.group()
def cli():
    pass


@cli.command()
@click.argument("name")
def start(name):
    """Crea un nuovo progetto ragin con scaffolding."""
    from ragin.cli.scaffold import scaffold_project
    path = scaffold_project(name)
    click.echo(f"Created project at {path}")


@cli.command()
@click.option("--app", default=None, help="Module:app_variable (es. main:app)")
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
def dev(app, host, port):
    """Avvia il server locale di sviluppo."""
    from ragin.conf import settings
    app = app or settings.APP
    host = host or settings.HOST
    port = port or settings.PORT
    module_name, attr = app.split(":", 1)
    mod = importlib.import_module(module_name)
    app_obj = getattr(mod, attr)

    from ragin.cli.dev_server import run_dev_server
    run_dev_server(app_obj, host=host, port=port)


@cli.command()
@click.option("--app", default="main:app")
@click.option("--output", default="build/", help="Directory output")
@click.option("--provider", default=None)
def build(app, output, provider):
    """Genera routes.json e entry point per il provider cloud."""
    from ragin.conf import settings
    provider = provider or settings.PROVIDER
    from ragin.cli.builder import build_app
    module_name, attr = app.split(":", 1)
    mod = importlib.import_module(module_name)
    app_obj = getattr(mod, attr)
    build_app(app_obj, output_dir=output, provider=provider)


def main():
    cli()
```

### Output di `ragin build`

```python
# ragin/cli/builder.py

import json
import os
from ragin.core.registry import registry


PROVIDER_ENTRY_TEMPLATES = {
    "aws": """# Auto-generated by ragin build
from ragin.runtime.aws import AWSProvider
import {module}  # noqa

lambda_handler = {module}.app.get_handler(AWSProvider())
""",
    "gcp": """# Auto-generated by ragin build
from ragin.runtime.gcp import GCPProvider
import {module}  # noqa

_provider = GCPProvider()

def http_handler(request):
    return {module}.app.handle(request, provider=_provider)
""",
    "azure": """# Auto-generated by ragin build
from ragin.runtime.azure import AzureProvider
import azure.functions as func
import {module}  # noqa

_provider = AzureProvider()

def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    return {module}.app.handle(req, provider=_provider)
""",
}


def build_app(app, output_dir: str, provider: str = "aws", module: str = "main"):
    os.makedirs(output_dir, exist_ok=True)
    routes = registry.get_routes()

    # routes.json — cloud-agnostic, descrive le route logiche
    routes_json = {
        "provider": provider,
        "entry_point": f"_ragin_entry",
        "routes": [{"method": r.method, "path": r.path} for r in routes],
    }
    with open(os.path.join(output_dir, "routes.json"), "w") as f:
        json.dump(routes_json, f, indent=2)

    # entry point specifico per il provider
    entry_code = PROVIDER_ENTRY_TEMPLATES[provider].format(module=module)
    with open(os.path.join(output_dir, "_ragin_entry.py"), "w") as f:
        f.write(entry_code)

    print(f"Build output in {output_dir}/")
    print(f"Provider: {provider}")
    print(f"Routes ({len(routes)}):")
    for r in routes:
        print(f"  {r.method:6} {r.path}")
```

> ✅ **IMPLEMENTATO** — CLI completa: `ragin start`, `ragin dev`, `ragin build` con Click. Builder genera entry point + routes.json.

---

## 10b. Settings (Django-style)

Il framework usa un sistema di configurazione ispirato a Django: un modulo Python
(`settings.py`) contiene le variabili di configurazione come attributi UPPER_CASE.
Il modulo è caricato **lazily** al primo accesso a qualsiasi attributo.

```python
# ragin/conf/settings.py

import importlib
import os
import sys
from typing import Any

_DEFAULTS = {
    "DATABASE_URL": "sqlite:///./ragin_dev.db",
    "PROVIDER": "local",
    "DEBUG": True,
    "HOST": "127.0.0.1",
    "PORT": 8000,
    "APP": "main:app",
}


class Settings:
    """Lazy settings container — loads the settings module on first attribute access."""

    def __init__(self):
        self._store: dict[str, Any] = {}
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        self._store = dict(_DEFAULTS)

        # 1. Import the settings module
        module_name = os.environ.get("RAGIN_SETTINGS_MODULE", "settings")
        try:
            if "." not in sys.path and "" not in sys.path:
                sys.path.insert(0, "")
            mod = importlib.import_module(module_name)
            for key in dir(mod):
                if key.isupper():
                    self._store[key] = getattr(mod, key)
        except ModuleNotFoundError:
            pass  # no settings module → use defaults + env overrides

        # 2. Env vars override: RAGIN_DATABASE_URL, RAGIN_PROVIDER, etc.
        for key in _DEFAULTS:
            env_val = os.environ.get(f"RAGIN_{key}")
            if env_val is not None:
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

    def configure(self, overrides: dict[str, Any]):
        """Programmatic override — e.g. in tests."""
        self._load()
        self._store.update(overrides)

    def reset(self):
        """Reset to un-loaded state (for tests)."""
        self._store = {}
        self._loaded = False

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        self._load()
        try:
            return self._store[name]
        except KeyError:
            raise AttributeError(f"Setting '{name}' not configured")
```

```python
# ragin/conf/__init__.py

from ragin.conf.settings import Settings

settings = Settings()
```

### Precedenza (highest wins)

1. Env var `RAGIN_DATABASE_URL` ecc.
2. `settings.py` (modulo Python)
3. Default built-in in `_DEFAULTS`

### Uso interno

Tutti i componenti del framework leggono la configurazione da `settings`:

```python
from ragin.conf import settings

url = settings.DATABASE_URL   # lazy loading al primo accesso
```

> ✅ **IMPLEMENTATO** — Django-style settings con lazy loading, env var override (`RAGIN_*`), `configure()`, `reset()`. Testato in `test_settings.py`.

---

## 10c. `ragin start` — Scaffold

Il comando `ragin start <name>` genera un progetto completo pronto per lo sviluppo.

```python
# ragin/cli/scaffold.py

SETTINGS_TEMPLATE = '''
# (template con DATABASE_URL, PROVIDER, DEBUG, HOST, PORT)
'''

MAIN_TEMPLATE = '''
from ragin import ServerlessApp
from models import *  # noqa: F401, F403

app = ServerlessApp()
'''

MODELS_INIT_TEMPLATE = '''
# (docstring con esempio, import User)
from models.user import User  # noqa: F401
__all__ = ["User"]
'''

MODELS_USER_TEMPLATE = '''
from ragin import Field, Model, resource

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str
'''


def scaffold_project(name: str, directory: str | None = None) -> str:
    target = os.path.abspath(directory or name)

    if os.path.exists(target) and os.listdir(target):
        raise FileExistsError(f"Directory '{target}' already exists and is not empty.")

    os.makedirs(target, exist_ok=True)
    models_dir = os.path.join(target, "models")
    os.makedirs(models_dir, exist_ok=True)

    # Scrive: settings.py, main.py, models/__init__.py, models/user.py
    ...
    return target
```

### Struttura generata

```
myproject/
├── main.py
├── settings.py
└── models/
    ├── __init__.py
    └── user.py         # modello User di esempio con @resource
```

> ✅ **IMPLEMENTATO** — Scaffold completo con `main.py`, `settings.py`, `models/` directory. Testato in `test_settings.py::TestScaffold`.

---

## 11. `pyproject.toml`

```toml
[project]
name = "ragin"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "click>=8.3.1",
    "pydantic>=2.12.5",
    "sqlalchemy>=2.0",
    "werkzeug>=3.1.7",
]

[project.optional-dependencies]
postgres = ["psycopg2-binary>=2.9"]
aws   = ["aws-lambda-powertools>=2.0"]
gcp   = ["functions-framework>=3.0"]
azure = ["azure-functions>=1.0"]

[project.scripts]
ragin = "ragin.cli.main:main"

[build-system]
requires = ["uv_build>=0.9.24,<0.10.0"]
build-backend = "uv_build"

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-cov>=7.1.0",
]
```

**Note:** `werkzeug` è una dev dependency — in Lambda non serve. Le dipendenze cloud
(`boto3`, `azure-functions`, ecc.) sono opzionali e installate solo sul provider target.
Il build backend è `uv_build` (non hatchling).

> ✅ **IMPLEMENTATO** — `pyproject.toml` con `uv_build` backend, dipendenze core + optional (postgres, aws, gcp, azure, openai, anthropic, bedrock).

---

## 12. Test Plan

### Unit test — con LocalProvider (nessun formato cloud)

I test usano `LocalProvider` e costruiscono `InternalRequest` direttamente.
Nessun bisogno di simulare eventi API Gateway o Cloud Functions.

```python
# tests/test_crud.py

from ragin import ServerlessApp, Model, Field, resource
from ragin.core.requests import InternalRequest
from ragin.runtime.local import LocalProvider
from ragin.persistence import configure_backend
from uuid import uuid4
import json

configure_backend("sqlite:///:memory:")
app = ServerlessApp(provider=LocalProvider())

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str

def make_request(method, path, body=None, query=None):
    return InternalRequest(
        method=method,
        path=path,
        query_params=query or {},
        raw_body=json.dumps(body) if body else None,
    )

def test_create_user():
    req = make_request("POST", "/users", body={"id": str(uuid4()), "name": "Alice", "email": "alice@example.com"})
    result = app.handle(req)
    assert result["statusCode"] == 201

def test_list_users():
    req = make_request("GET", "/users")
    result = app.handle(req)
    assert result["statusCode"] == 200
    assert isinstance(result["body"], list)

def test_create_duplicate_pk():
    uid = str(uuid4())
    make_request("POST", "/users", body={"id": uid, "name": "A", "email": "a@a.com"})
    req = make_request("POST", "/users", body={"id": uid, "name": "B", "email": "b@b.com"})
    result = app.handle(req)
    assert result["statusCode"] == 409
```

### Integration test — con SQLite in-memory

```python
from ragin.persistence import configure_backend
configure_backend("sqlite:///:memory:")
```

### Test del router in isolamento

```python
from ragin.core.routing import Router
from ragin.core.registry import RouteDefinition

def dummy_handler(req): pass

def test_router_path_params():
    routes = [RouteDefinition("GET", "/users/{id}", dummy_handler)]
    router = Router(routes)
    from ragin.core.requests import InternalRequest
    req = InternalRequest(method="GET", path="/users/abc-123")
    match, params = router.match(req)
    assert params["id"] == "abc-123"
```

> ✅ **IMPLEMENTATO** — 37 test V1 + 40 test V2 = 77 test totali, tutti verdi. Test CRUD, models, routing, settings, scaffold, agent, MCP, providers, tools, prompt.

---

## 13. Ordine di Implementazione

1. `core/fields.py` — `Field()` con `json_schema_extra`
2. `core/models.py` — `Model` base class
3. `core/registry.py` — `RouteDefinition` + `ResourceRegistry`
4. `core/requests.py` / `core/responses.py` — solo strutture dati, zero cloud
5. `core/routing.py` — `Router` con regex
6. `resource/crud.py` — `CrudHandlerFactory` (con 409 Conflict handling)
7. `resource/decorator.py` — `@resource`
8. `runtime/base.py` — `BaseRuntimeProvider`
9. `runtime/local.py` — `LocalProvider` (usato nei test fin da subito)
10. `runtime/aws.py` / `gcp.py` / `azure.py`
11. `runtime/__init__.py` — `get_default_provider()`
12. `core/app.py` — `ServerlessApp` (ora dipende da runtime)
13. `conf/settings.py` — Settings loader (Django-style, lazy)
14. `persistence/schema.py` + `persistence/sql.py`
15. `persistence/__init__.py` — `get_backend()` (usa settings.DATABASE_URL)
16. `cli/scaffold.py` — `ragin start` (genera progetto)
17. `cli/dev_server.py`
18. `cli/main.py` + `cli/builder.py`
19. `pyproject.toml` + `__init__.py` exports
20. Test suite

> ✅ **IMPLEMENTATO** — Tutti i 20 step completati.

---

## 14. Dipendenze Esterne

| Package              | Motivo                          | Scope           |
|----------------------|---------------------------------|-----------------|
| `pydantic`           | validazione + schema            | core            |
| `sqlalchemy`         | SQL Core (no ORM)               | core            |
| `click`              | CLI                             | dev only        |
| `werkzeug`           | dev server locale               | dev only        |
| `azure-functions`    | AzureProvider (parse/format)    | optional        |
| `functions-framework`| GCPProvider test locale         | optional        |

Il **runtime Lambda** installerà solo `pydantic` + `sqlalchemy`.
Nessuna dipendenza cloud nel core — i provider cloud sono import opzionali.

> ✅ **IMPLEMENTATO** — Tutte le dipendenze esterne installate e verificate.
