# ragin V2 Core — Implementation Spec

> Agent Layer + MCP Server + Multi-Provider LLM

---

## Scope V2

Prerequisito: **V1 Core completato** (Model, @resource, CRUD, runtime provider layer, settings, CLI).

Cosa è incluso in V2:
- `@agent` decorator — genera un agente AI collegato a uno o più modelli
- **Agent runner** — loop LLM con tool calling automatico
- **System prompt auto-generato** dallo schema del modello + descrizioni Field
- **Tool binding CRUD → MCP** — ogni operazione CRUD diventa un tool invocabile
- **Tool custom** su agente (`@MyAgent.tool`)
- **MCP server Lambda** — implementa Model Context Protocol over Streamable HTTP
- **Multi-Provider LLM** — adapter per OpenAI, Anthropic, AWS Bedrock
- **Endpoint agente** — `POST /<resource>/agent`
- `ragin build` aggiornato — genera lambda_agent + lambda_mcp
- Stateless by default, con opzione `thread_id` per history esterna

Cosa NON è incluso in V2:
- Provider LangChain, PydanticAI (V3)
- Conversation history persistente DynamoDB (V3)
- Hooks before/after (V3)
- Multi-model agent (V3)
- Streaming LLM response (V3)
- Auth/permissions (V3)

---

## Struttura File Aggiunti in V2

```
ragin/
  # ... tutto V1 invariato ...

  agent/
    __init__.py            # export: agent decorator
    decorator.py           # @agent
    runner.py              # AgentRunner — loop LLM + tool calls
    prompt.py              # generazione system prompt da schema modello
    tools.py               # ToolRegistry — binding CRUD → tool schema

  mcp/
    __init__.py
    server.py              # MCP Lambda handler (Streamable HTTP)
    tools.py               # generazione tool JSON schema da modelli
    transport.py           # Streamable HTTP transport layer

  providers/
    __init__.py            # export provider classes
    base.py                # BaseProvider ABC
    openai.py              # OpenAIProvider
    anthropic.py           # AnthropicProvider
    bedrock.py             # BedrockProvider
```

### Nuove dipendenze opzionali

```toml
[project.optional-dependencies]
# ... V1 invariate ...
openai    = ["openai>=1.0"]
anthropic = ["anthropic>=0.30"]
bedrock   = ["boto3>=1.34"]
```

---

## 1. `@agent` Decorator

Il decorator registra un agente nel `ResourceRegistry`, genera endpoint e tool binding.

```python
# ragin/agent/decorator.py

from ragin.core.registry import registry, RouteDefinition
from ragin.agent.runner import AgentRunner
from ragin.agent.prompt import generate_system_prompt
from ragin.agent.tools import build_crud_tools


def agent(
    model=None,                     # Model class o lista di Model classes
    provider=None,                  # istanza di BaseProvider (OpenAI, Anthropic, ...)
    description: str = "",          # aggiunto al system prompt
    tools: list[str] | None = None, # "crud" (default), lista operazioni, o nomi custom
    history_backend=None,           # None = stateless, futuro: "dynamodb"
):
    def decorator(cls):
        models = [model] if not isinstance(model, list) else model
        tool_defs = _resolve_tools(models, tools or ["crud"])
        system_prompt = generate_system_prompt(models, description)

        runner = AgentRunner(
            provider=provider,
            system_prompt=system_prompt,
            tools=tool_defs,
        )

        # Registra l'endpoint POST /<resource>/agent
        for m in models:
            resource_name = m.__name__.lower() + "s"
            path = f"/{resource_name}/agent"

            def _make_handler(r=runner):
                def handler(request):
                    message = request.json_body.get("message", "")
                    thread_id = request.json_body.get("thread_id")
                    result = r.run(message, thread_id=thread_id)
                    return InternalResponse.ok(result)
                return handler

            registry.register_route(RouteDefinition(
                method="POST",
                path=path,
                handler=_make_handler(),
                model=m,
                operation="agent",
            ))

        # Supporto per tool custom: @MyAgent.tool
        cls._runner = runner
        cls._tool_defs = tool_defs

        @classmethod
        def tool_decorator(cls, fn):
            """Registra un tool custom sull'agente."""
            runner.register_custom_tool(fn)
            return fn

        cls.tool = tool_decorator
        return cls

    return decorator


def _resolve_tools(models, tools_config):
    """Risolve la configurazione tools in una lista di ToolDefinition."""
    all_tools = []
    for m in models:
        if tools_config == ["crud"] or "crud" in tools_config:
            all_tools.extend(build_crud_tools(m))
        else:
            for op in tools_config:
                all_tools.extend(build_crud_tools(m, operations=[op]))
    return all_tools
```

### Uso nell'app utente

```python
from ragin import ServerlessApp, Model, Field, resource, agent
from ragin.providers import OpenAIProvider

app = ServerlessApp()

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str = Field(description="Indirizzo email dell'utente")
    role: str = "member"


@agent(
    model=User,
    provider=OpenAIProvider(model="gpt-4o"),
    description="Manages user records. Can create, list, retrieve, update and delete users.",
)
class UserAgent:
    pass
```

Genera automaticamente:
- Endpoint `POST /users/agent`
- 5 tool MCP: `create_user`, `list_users`, `get_user`, `update_user`, `delete_user`
- System prompt con schema User e descrizione

---

## 2. System Prompt Auto-Generation

Il system prompt è generato dallo schema del modello. Include: nome del modello,
campi con tipi e `description` da Field, operazioni disponibili.

```python
# ragin/agent/prompt.py

from ragin.core.fields import get_ragin_meta


def generate_system_prompt(models: list[type], description: str = "") -> str:
    """
    Genera il system prompt dall'elenco di modelli registrati.
    Includa: nomi, campi, tipi, descrizioni, operazioni disponibili.
    """
    parts = []
    parts.append("You are an AI assistant that manages the following data models.\n")

    if description:
        parts.append(f"{description}\n")

    for model_cls in models:
        parts.append(f"## {model_cls.__name__}")
        parts.append(f"Table: {model_cls.ragin_table_name()}")
        parts.append("Fields:")

        for name, field_info in model_cls.model_fields.items():
            meta = get_ragin_meta(model_cls, name)
            type_name = _type_label(field_info)
            desc = field_info.description or ""
            pk = " (primary key)" if meta.get("primary_key") else ""
            parts.append(f"  - {name}: {type_name}{pk}{' — ' + desc if desc else ''}")

        parts.append("")

    parts.append("Use the available tools to perform operations on these models.")
    parts.append("Always confirm actions with a clear response to the user.")

    return "\n".join(parts)


def _type_label(field_info) -> str:
    ann = field_info.annotation
    return getattr(ann, "__name__", str(ann))
```

### Esempio di system prompt generato

Per il modello `User` con description `"Manages user records..."`:

```
You are an AI assistant that manages the following data models.

Manages user records. Can create, list, retrieve, update and delete users.

## User
Table: users
Fields:
  - id: str (primary key)
  - name: str
  - email: str — Indirizzo email dell'utente
  - role: str

Use the available tools to perform operations on these models.
Always confirm actions with a clear response to the user.
```

---

## 3. Tool Binding — CRUD → MCP Tools

Ogni operazione CRUD registrata genera un tool con JSON schema derivato dal modello.

```python
# ragin/agent/tools.py

from dataclasses import dataclass, field
from typing import Any, Callable

from ragin.core.fields import get_ragin_meta


@dataclass
class ToolDefinition:
    """Descrizione di un tool MCP invocabile dall'agente."""
    name: str                          # "create_user", "list_users", ecc.
    description: str                   # per il LLM
    parameters: dict[str, Any]         # JSON Schema dei parametri
    handler: Callable                  # funzione che esegue il tool
    model: type | None = None


def build_crud_tools(
    model_cls: type,
    operations: list[str] | None = None,
) -> list[ToolDefinition]:
    """
    Genera ToolDefinition per le operazioni CRUD del modello.
    Se operations è None, genera tutte e 5.
    """
    ops = operations or ["create", "list", "retrieve", "update", "delete"]
    resource_name = model_cls.__name__.lower() + "s"
    singular = model_cls.__name__.lower()
    tools = []

    schema = _model_json_schema(model_cls)
    pk_field = model_cls.primary_key_field()

    if "create" in ops:
        tools.append(ToolDefinition(
            name=f"create_{singular}",
            description=f"Create a new {singular}.",
            parameters=schema,
            handler=_make_crud_caller("POST", f"/{resource_name}"),
            model=model_cls,
        ))

    if "list" in ops:
        tools.append(ToolDefinition(
            name=f"list_{resource_name}",
            description=f"List {resource_name}. Supports filters as query parameters.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 100},
                    "offset": {"type": "integer", "default": 0},
                    **{k: _field_schema(v) for k, v in model_cls.model_fields.items()
                       if not get_ragin_meta(model_cls, k).get("primary_key")},
                },
            },
            handler=_make_crud_caller("GET", f"/{resource_name}"),
            model=model_cls,
        ))

    if "retrieve" in ops:
        tools.append(ToolDefinition(
            name=f"get_{singular}",
            description=f"Retrieve a single {singular} by {pk_field}.",
            parameters={
                "type": "object",
                "properties": {pk_field: {"type": "string"}},
                "required": [pk_field],
            },
            handler=_make_crud_caller("GET", f"/{resource_name}/{{id}}"),
            model=model_cls,
        ))

    if "update" in ops:
        tools.append(ToolDefinition(
            name=f"update_{singular}",
            description=f"Update an existing {singular}. Pass only the fields to change.",
            parameters={
                "type": "object",
                "properties": {
                    pk_field: {"type": "string"},
                    **{k: _field_schema(v) for k, v in model_cls.model_fields.items()
                       if k != pk_field},
                },
                "required": [pk_field],
            },
            handler=_make_crud_caller("PATCH", f"/{resource_name}/{{id}}"),
            model=model_cls,
        ))

    if "delete" in ops:
        tools.append(ToolDefinition(
            name=f"delete_{singular}",
            description=f"Delete a {singular} by {pk_field}.",
            parameters={
                "type": "object",
                "properties": {pk_field: {"type": "string"}},
                "required": [pk_field],
            },
            handler=_make_crud_caller("DELETE", f"/{resource_name}/{{id}}"),
            model=model_cls,
        ))

    return tools


def _model_json_schema(model_cls: type) -> dict:
    """Genera il JSON Schema completo dei parametri per create."""
    return model_cls.model_json_schema()


def _field_schema(field_info) -> dict:
    """Genera lo schema JSON di un singolo campo."""
    ann = field_info.annotation
    type_name = getattr(ann, "__name__", str(ann))
    type_map = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}
    return {"type": type_map.get(type_name, "string")}


def _make_crud_caller(method: str, path_template: str) -> Callable:
    """
    Crea un handler che costruisce un InternalRequest e lo passa
    al ServerlessApp. Il tool chiama la stessa API CRUD interna.
    """
    def tool_handler(arguments: dict) -> dict:
        from ragin.core.requests import InternalRequest
        from ragin.core.registry import registry
        from ragin.core.routing import Router
        import json

        # Risolve {id} nel path
        path = path_template
        if "{id}" in path and "id" in arguments:
            path = path.replace("{id}", str(arguments["id"]))

        if method == "GET":
            query = {k: v for k, v in arguments.items() if k != "id"}
            body = None
        else:
            query = {}
            body = {k: v for k, v in arguments.items() if k != "id"} if method != "DELETE" else None

        request = InternalRequest(
            method=method,
            path=path,
            query_params=query,
            raw_body=json.dumps(body) if body else None,
        )

        router = Router(registry.get_routes())
        match = router.match(request)
        if match is None:
            return {"error": "Route not found"}

        route, path_params = match
        request.path_params = path_params
        response = route.handler(request)
        return response.body

    return tool_handler
```

### Tool JSON Schema (formato OpenAI / MCP)

Il tool `create_user` genera:

```json
{
  "name": "create_user",
  "description": "Create a new user.",
  "parameters": {
    "type": "object",
    "properties": {
      "id":    {"type": "string"},
      "name":  {"type": "string"},
      "email": {"type": "string", "description": "Indirizzo email dell'utente"},
      "role":  {"type": "string", "default": "member"}
    },
    "required": ["id", "name", "email"]
  }
}
```

---

## 4. AgentRunner — Loop LLM + Tool Calls

Il runner gestisce il loop conversazionale: invia il messaggio al LLM, esegue
i tool call, reinvia i risultati fino a ottenere una risposta finale.

```python
# ragin/agent/runner.py

from dataclasses import dataclass, field
from typing import Any

from ragin.agent.tools import ToolDefinition
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall


@dataclass
class AgentResult:
    """Risultato finale dell'agente, ritornato all'utente."""
    message: str
    tool_calls: list[dict] = field(default_factory=list)   # per debug
    thread_id: str | None = None


class AgentRunner:
    """
    Stateless agent runner. Ogni chiamata a run() è indipendente.
    Il loop:
      1. Costruisce i messaggi (system + user)
      2. Chiama il LLM con i tool disponibili
      3. Se il LLM ritorna tool_calls → esegue i tool, aggiunge i risultati, ripete
      4. Se il LLM ritorna un messaggio finale → ritorna AgentResult
    """

    MAX_ITERATIONS = 10   # safety brake

    def __init__(
        self,
        provider: BaseProvider,
        system_prompt: str,
        tools: list[ToolDefinition],
    ):
        self.provider = provider
        self.system_prompt = system_prompt
        self.tools = {t.name: t for t in tools}
        self.tool_schemas = [self._to_provider_schema(t) for t in tools]

    def register_custom_tool(self, fn):
        """Registra un tool custom definito dall'utente."""
        import inspect
        sig = inspect.signature(fn)
        params = {
            "type": "object",
            "properties": {
                name: {"type": "string"} for name in sig.parameters
            },
        }
        tool_def = ToolDefinition(
            name=fn.__name__,
            description=fn.__doc__ or "",
            parameters=params,
            handler=lambda args: fn(**args),
        )
        self.tools[tool_def.name] = tool_def
        self.tool_schemas.append(self._to_provider_schema(tool_def))

    def run(self, user_message: str, thread_id: str | None = None) -> dict:
        """
        Esegue l'agente. Stateless: nessun stato persistente tra chiamate.
        thread_id è passato al provider per future implementazioni di history.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        all_tool_calls = []

        for _ in range(self.MAX_ITERATIONS):
            response: AgentResponse = self.provider.complete(
                messages=messages,
                tools=self.tool_schemas,
            )

            if not response.tool_calls:
                # Risposta finale del LLM
                return {
                    "message": response.content,
                    "tool_calls": all_tool_calls,
                    "thread_id": thread_id,
                }

            # Esegue i tool_calls
            for tc in response.tool_calls:
                tool = self.tools.get(tc.name)
                if tool is None:
                    result = {"error": f"Unknown tool: {tc.name}"}
                else:
                    try:
                        result = tool.handler(tc.arguments)
                    except Exception as e:
                        result = {"error": str(e)}

                all_tool_calls.append({
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "result": result,
                })

                # Aggiunge il risultato del tool ai messaggi
                messages.append({
                    "role": "assistant",
                    "tool_calls": [tc.to_dict()],
                    "content": None,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                })

        # Safety: troppe iterazioni
        return {
            "message": "Agent reached maximum iterations without a final response.",
            "tool_calls": all_tool_calls,
            "thread_id": thread_id,
        }

    def _to_provider_schema(self, tool: ToolDefinition) -> dict:
        """Converte ToolDefinition nel formato tool schema del provider."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
```

### Flusso di una richiesta

```
POST /users/agent  {"message": "Crea un utente Alice con email alice@example.com"}
  │
  ▼
AgentRunner.run("Crea un utente Alice...")
  │
  ├── 1. provider.complete(messages, tools) → LLM
  │      LLM ritorna: tool_call create_user(name="Alice", email="alice@example.com", ...)
  │
  ├── 2. Esegue create_user → chiama CRUD handler internamente → DB insert
  │      Risultato: {"id": "abc-123", "name": "Alice", ...}
  │
  ├── 3. provider.complete(messages + tool_result, tools) → LLM
  │      LLM ritorna: "Ho creato l'utente Alice con successo. ID: abc-123"
  │
  └── 4. Return AgentResult
         {"message": "Ho creato l'utente Alice...", "tool_calls": [...]}
```

---

## 5. BaseProvider — Interfaccia LLM

Ogni provider LLM implementa una sola interfaccia: `complete()`.
Riceve messaggi e tool schemas, ritorna una risposta con eventuale tool_calls.

```python
# ragin/providers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Un singolo tool call richiesto dal LLM."""
    id: str                     # identificatore univoco (generato dal LLM)
    name: str                   # nome del tool
    arguments: dict[str, Any]   # argomenti parsati

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass
class AgentResponse:
    """Risposta del provider LLM."""
    content: str | None = None           # testo se risposta finale
    tool_calls: list[ToolCall] = field(default_factory=list)  # se il LLM vuole chiamare tool


class BaseProvider(ABC):
    """
    Interfaccia per i provider LLM.
    Ogni provider converte internamente da/a il formato nativo del LLM.
    """

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AgentResponse:
        """
        Invia messaggi al LLM e ritorna la risposta.

        messages: lista di messaggi nel formato OpenAI-like:
            [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, ...]

        tools: lista di tool schemas nel formato OpenAI function calling:
            [{"type": "function", "function": {"name": ..., "parameters": ...}}]

        Ritorna AgentResponse con content (se risposta finale) o tool_calls (se chiama tool).
        """
        ...
```

---

## 6. Provider Implementations

### 6.1 OpenAI Provider

```python
# ragin/providers/openai.py

import json
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall


class OpenAIProvider(BaseProvider):
    """Provider per OpenAI API (gpt-4o, gpt-4o-mini, ecc.)."""

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None):
        self.model = model
        self.api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai
            kwargs = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> AgentResponse:
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        if message.tool_calls:
            return AgentResponse(
                content=message.content,
                tool_calls=[
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                    for tc in message.tool_calls
                ],
            )

        return AgentResponse(content=message.content)
```

### 6.2 Anthropic Provider

```python
# ragin/providers/anthropic.py

import json
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall


class AnthropicProvider(BaseProvider):
    """Provider per Anthropic API (Claude 3.5, Claude 4, ecc.)."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str | None = None):
        self.model = model
        self.api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic
            kwargs = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> AgentResponse:
        # Anthropic usa un formato diverso per i tool
        system = None
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                filtered.append(m)

        kwargs = {"model": self.model, "messages": filtered, "max_tokens": 4096}
        if system:
            kwargs["system"] = system

        if tools:
            # Converte da formato OpenAI a formato Anthropic
            kwargs["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ]

        response = self.client.messages.create(**kwargs)

        tool_calls = []
        content_parts = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))

        content = "\n".join(content_parts) if content_parts else None

        if tool_calls:
            return AgentResponse(content=content, tool_calls=tool_calls)

        return AgentResponse(content=content)
```

### 6.3 Bedrock Provider

```python
# ragin/providers/bedrock.py

import json
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall


class BedrockProvider(BaseProvider):
    """Provider per AWS Bedrock (Claude, Llama, Titan, ecc.)."""

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
        region: str = "us-east-1",
    ):
        self.model_id = model_id
        self.region = region
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> AgentResponse:
        system = []
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system.append({"text": m["content"]})
            else:
                filtered.append(self._convert_message(m))

        kwargs = {
            "modelId": self.model_id,
            "messages": filtered,
            "inferenceConfig": {"maxTokens": 4096},
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t["function"]["name"],
                            "description": t["function"]["description"],
                            "inputSchema": {"json": t["function"]["parameters"]},
                        }
                    }
                    for t in tools
                ]
            }

        response = self.client.converse(**kwargs)
        output = response["output"]["message"]

        tool_calls = []
        content_parts = []

        for block in output["content"]:
            if "text" in block:
                content_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(ToolCall(
                    id=tu["toolUseId"],
                    name=tu["name"],
                    arguments=tu["input"],
                ))

        content = "\n".join(content_parts) if content_parts else None

        if tool_calls:
            return AgentResponse(content=content, tool_calls=tool_calls)

        return AgentResponse(content=content)

    def _convert_message(self, msg: dict) -> dict:
        """Converte da formato OpenAI-like a formato Bedrock Converse."""
        if msg["role"] == "tool":
            return {
                "role": "user",
                "content": [{
                    "toolResult": {
                        "toolUseId": msg["tool_call_id"],
                        "content": [{"text": msg["content"]}],
                    }
                }],
            }
        if msg.get("tool_calls"):
            return {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": tc["id"],
                            "name": tc["function"]["name"],
                            "input": tc["function"]["arguments"],
                        }
                    }
                    for tc in msg["tool_calls"]
                ],
            }
        return {
            "role": msg["role"],
            "content": [{"text": msg["content"] or ""}],
        }
```

### Provider exports

```python
# ragin/providers/__init__.py

from ragin.providers.base import BaseProvider, AgentResponse, ToolCall

__all__ = ["BaseProvider", "AgentResponse", "ToolCall"]

# Lazy imports per non richiedere le dipendenze opzionali
def __getattr__(name):
    if name == "OpenAIProvider":
        from ragin.providers.openai import OpenAIProvider
        return OpenAIProvider
    if name == "AnthropicProvider":
        from ragin.providers.anthropic import AnthropicProvider
        return AnthropicProvider
    if name == "BedrockProvider":
        from ragin.providers.bedrock import BedrockProvider
        return BedrockProvider
    raise AttributeError(f"module 'ragin.providers' has no attribute {name}")
```

---

## 7. MCP Server Lambda

Il MCP server implementa il [Model Context Protocol](https://modelcontextprotocol.io)
via Streamable HTTP. Espone i tool generati dai modelli come tool MCP standard,
consumabili dall'agente ragin o da qualsiasi client MCP esterno.

### 7.1 Tool Schema Generation

```python
# ragin/mcp/tools.py

from ragin.agent.tools import ToolDefinition


def tool_to_mcp_schema(tool: ToolDefinition) -> dict:
    """Converte un ToolDefinition nel formato MCP tools/list."""
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.parameters,
    }


def build_mcp_tool_list(tools: list[ToolDefinition]) -> list[dict]:
    """Genera la lista completa per la response MCP tools/list."""
    return [tool_to_mcp_schema(t) for t in tools]
```

### 7.2 MCP Handler

```python
# ragin/mcp/server.py

import json
from ragin.agent.tools import ToolDefinition


class MCPServer:
    """
    Handler per richieste MCP over Streamable HTTP.
    Implementa: initialize, tools/list, tools/call.
    """

    def __init__(self, tools: list[ToolDefinition]):
        self.tools = {t.name: t for t in tools}

    def handle(self, request_body: dict) -> dict:
        """Gestisce una singola richiesta JSON-RPC MCP."""
        method = request_body.get("method")
        params = request_body.get("params", {})
        req_id = request_body.get("id")

        if method == "initialize":
            return self._jsonrpc_response(req_id, {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ragin-mcp", "version": "0.1.0"},
            })

        if method == "tools/list":
            from ragin.mcp.tools import build_mcp_tool_list
            tool_list = build_mcp_tool_list(list(self.tools.values()))
            return self._jsonrpc_response(req_id, {"tools": tool_list})

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            tool = self.tools.get(tool_name)

            if tool is None:
                return self._jsonrpc_error(req_id, -32602, f"Unknown tool: {tool_name}")

            try:
                result = tool.handler(arguments)
                return self._jsonrpc_response(req_id, {
                    "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                })
            except Exception as e:
                return self._jsonrpc_response(req_id, {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                })

        return self._jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    def _jsonrpc_response(self, req_id, result) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _jsonrpc_error(self, req_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
```

### 7.3 MCP Lambda Entry Point

```python
# build/_ragin_mcp_entry.py (generato da ragin build)

import json
from ragin.mcp.server import MCPServer
from ragin.agent.tools import build_crud_tools
import main  # app utente — i @resource sono registrati all'import

# Raccoglie tutti i tool da tutti i modelli registrati
from ragin.core.registry import registry
all_tools = []
for model_cls in registry._models.values():
    all_tools.extend(build_crud_tools(model_cls))

mcp = MCPServer(all_tools)


def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))
    result = mcp.handle(body)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result),
    }
```

### Consumo da client MCP esterno

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "ragin-users": {
      "url": "https://abc123.execute-api.eu-west-1.amazonaws.com/mcp"
    }
  }
}
```

---

## 8. Aggiornamenti al Registry

Il `ResourceRegistry` V2 gestisce anche agenti e tool MCP.

```python
# Aggiunte a ragin/core/registry.py

@dataclass
class AgentDefinition:
    model: type | list[type]
    provider: object           # BaseProvider instance
    runner: object             # AgentRunner instance
    endpoint: str              # "/users/agent"

class ResourceRegistry:
    # ... V1 fields ...
    _agents: dict[str, AgentDefinition] = {}

    def register_agent(self, name: str, agent_def: AgentDefinition):
        self._agents[name] = agent_def

    def get_agents(self) -> dict[str, AgentDefinition]:
        return dict(self._agents)
```

---

## 9. Aggiornamenti al Build

`ragin build` in V2 genera tre entry point:

```
build/
  _ragin_entry.py          # CRUD Lambda (invariato da V1)
  _ragin_agent_entry.py    # Agent Lambda
  _ragin_mcp_entry.py      # MCP Lambda
  routes.json              # tutte le route inclusi /agent e /mcp
```

```python
# Aggiunta a ragin/cli/builder.py

AGENT_ENTRY_TEMPLATE = """# Auto-generated by ragin build
from ragin.runtime.{provider_module} import {provider_class}
import {module}  # noqa

# L'app contiene già gli agent registrati via @agent
_handler = {module}.app.get_handler({provider_class}())
"""

MCP_ENTRY_TEMPLATE = """# Auto-generated by ragin build
import json
from ragin.mcp.server import MCPServer
from ragin.agent.tools import build_crud_tools
from ragin.core.registry import registry
import {module}  # noqa

all_tools = []
for model_cls in registry._models.values():
    all_tools.extend(build_crud_tools(model_cls))

mcp = MCPServer(all_tools)

def lambda_handler(event, context):
    body = json.loads(event.get("body", "{{}}"))
    result = mcp.handle(body)
    return {{
        "statusCode": 200,
        "headers": {{"Content-Type": "application/json"}},
        "body": json.dumps(result),
    }}
"""
```

### routes.json aggiornato

```json
{
  "provider": "aws",
  "lambdas": {
    "crud": {
      "entry_point": "_ragin_entry",
      "routes": [
        {"method": "POST", "path": "/users"},
        {"method": "GET",  "path": "/users"},
        {"method": "GET",  "path": "/users/{id}"},
        {"method": "PATCH","path": "/users/{id}"},
        {"method": "DELETE","path": "/users/{id}"}
      ]
    },
    "agent": {
      "entry_point": "_ragin_agent_entry",
      "routes": [
        {"method": "POST", "path": "/users/agent"}
      ]
    },
    "mcp": {
      "entry_point": "_ragin_mcp_entry",
      "routes": [
        {"method": "POST", "path": "/mcp"}
      ]
    }
  }
}
```

---

## 10. Export

```python
# ragin/__init__.py  (aggiornato per V2)

from ragin.core.app import ServerlessApp
from ragin.core.fields import Field
from ragin.core.models import Model
from ragin.resource.decorator import resource
from ragin.agent.decorator import agent          # NEW V2

__all__ = ["ServerlessApp", "Field", "Model", "resource", "agent"]
```

---

## 11. Test Plan

### Test Agente (con mock LLM)

```python
# tests/test_agent.py

from unittest.mock import MagicMock
from ragin import ServerlessApp, Model, Field, resource, agent
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall
from ragin.core.requests import InternalRequest
import json


class MockProvider(BaseProvider):
    """Provider che ritorna risposte predefinite."""

    def __init__(self, responses: list[AgentResponse]):
        self._responses = list(responses)
        self._call_count = 0

    def complete(self, messages, tools=None):
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp


def test_agent_simple_message():
    """L'agente risponde senza tool calls."""
    mock = MockProvider([
        AgentResponse(content="Ciao, come posso aiutarti?"),
    ])

    @resource(operations=["crud"])
    class User(Model):
        id: str = Field(primary_key=True)
        name: str

    @agent(model=User, provider=mock, description="Test agent")
    class UserAgent:
        pass

    req = InternalRequest(
        method="POST",
        path="/users/agent",
        raw_body=json.dumps({"message": "Ciao"}),
    )
    app = ServerlessApp()
    result = app.handle(req)
    assert result["statusCode"] == 200
    assert result["body"]["message"] == "Ciao, come posso aiutarti?"


def test_agent_tool_call():
    """L'agente chiama un tool CRUD e poi risponde."""
    mock = MockProvider([
        # Prima chiamata: il LLM vuole creare un utente
        AgentResponse(tool_calls=[
            ToolCall(id="tc1", name="create_user", arguments={
                "id": "u1", "name": "Alice",
            }),
        ]),
        # Seconda chiamata: il LLM risponde con il risultato
        AgentResponse(content="Ho creato l'utente Alice."),
    ])

    @resource(operations=["crud"])
    class User(Model):
        id: str = Field(primary_key=True)
        name: str

    @agent(model=User, provider=mock, description="Test agent")
    class UserAgent:
        pass

    req = InternalRequest(
        method="POST",
        path="/users/agent",
        raw_body=json.dumps({"message": "Crea un utente Alice"}),
    )
    app = ServerlessApp()
    result = app.handle(req)
    assert result["statusCode"] == 200
    assert "Alice" in result["body"]["message"]
    assert len(result["body"]["tool_calls"]) == 1
```

### Test MCP Server

```python
# tests/test_mcp.py

from ragin.mcp.server import MCPServer
from ragin.agent.tools import ToolDefinition


def _echo_handler(arguments):
    return {"echo": arguments}


def test_mcp_tools_list():
    tools = [ToolDefinition(
        name="echo", description="Echo tool",
        parameters={"type": "object", "properties": {"msg": {"type": "string"}}},
        handler=_echo_handler,
    )]
    mcp = MCPServer(tools)

    result = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert result["result"]["tools"][0]["name"] == "echo"


def test_mcp_tools_call():
    tools = [ToolDefinition(
        name="echo", description="Echo tool",
        parameters={"type": "object", "properties": {"msg": {"type": "string"}}},
        handler=_echo_handler,
    )]
    mcp = MCPServer(tools)

    result = mcp.handle({
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"msg": "hello"}},
    })
    assert '"echo"' in result["result"]["content"][0]["text"]


def test_mcp_unknown_tool():
    mcp = MCPServer([])
    result = mcp.handle({
        "jsonrpc": "2.0", "id": 3,
        "method": "tools/call",
        "params": {"name": "nope", "arguments": {}},
    })
    assert "error" in result
```

### Test Tool Binding

```python
# tests/test_tools.py

from ragin import Model, Field, resource
from ragin.agent.tools import build_crud_tools


def test_crud_tools_generated():
    @resource(operations=["crud"])
    class User(Model):
        id: str = Field(primary_key=True)
        name: str
        email: str

    tools = build_crud_tools(User)
    names = [t.name for t in tools]
    assert "create_user" in names
    assert "list_users" in names
    assert "get_user" in names
    assert "update_user" in names
    assert "delete_user" in names


def test_tool_parameters_match_model():
    @resource(operations=["crud"])
    class User(Model):
        id: str = Field(primary_key=True)
        name: str
        email: str

    tools = build_crud_tools(User)
    create_tool = next(t for t in tools if t.name == "create_user")
    props = create_tool.parameters.get("properties", {})
    assert "name" in props or "id" in props  # Pydantic JSON schema
```

### Test System Prompt

```python
# tests/test_prompt.py

from ragin import Model, Field
from ragin.agent.prompt import generate_system_prompt


def test_system_prompt_contains_model_info():
    class User(Model):
        id: str = Field(primary_key=True)
        name: str
        email: str = Field(description="Email address")

    prompt = generate_system_prompt([User], "Manages users.")
    assert "User" in prompt
    assert "email" in prompt
    assert "Email address" in prompt
    assert "Manages users." in prompt
```

---

## 12. Ordine di Implementazione

1. `providers/base.py` — `BaseProvider`, `AgentResponse`, `ToolCall`
2. `providers/openai.py` — `OpenAIProvider`
3. `agent/tools.py` — `ToolDefinition`, `build_crud_tools()`
4. `agent/prompt.py` — `generate_system_prompt()`
5. `agent/runner.py` — `AgentRunner`
6. `agent/decorator.py` — `@agent`
7. `mcp/tools.py` — `tool_to_mcp_schema()`
8. `mcp/server.py` — `MCPServer`
9. `providers/anthropic.py` — `AnthropicProvider`
10. `providers/bedrock.py` — `BedrockProvider`
11. `providers/__init__.py` — lazy exports
12. `core/registry.py` — aggiunte V2 (`AgentDefinition`)
13. `cli/builder.py` — genera agent + mcp entry points
14. `__init__.py` — export `agent`
15. Test suite (con MockProvider)

---

## 13. Dipendenze V2

| Package      | Motivo                        | Scope          |
|--------------|-------------------------------|----------------|
| `openai`     | OpenAIProvider                | optional       |
| `anthropic`  | AnthropicProvider             | optional       |
| `boto3`      | BedrockProvider (Converse API)| optional       |

Nessuna nuova dipendenza **core** — i provider LLM sono tutti opzionali.
Il codice agent/mcp dipende solo dai moduli ragin V1.

---

## 14. Non-Goals (V2)

- Streaming response (il LLM risponde in un colpo)
- Conversation history persistente (stateless, thread_id è solo un passthrough)
- Auth/permissions sugli endpoint agent
- Multi-agent orchestration
- Provider LangChain / PydanticAI (V3)
- Deploy automatico (rimane build-only)
