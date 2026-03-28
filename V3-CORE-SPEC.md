# ragin V3 Core — Implementation Spec

> Semantic Layer · Embeddings · Vector Search · AI-Native Backend

---

## Scope V3

Prerequisito: **V1 + V2 completati** (Model, @resource, CRUD, @agent, providers, MCP server).

Cosa è incluso in V3:
- `Field(embedding=True)` — marca i campi per generazione embedding automatica
- `EmbeddingProvider` ABC — astrazione per generare embeddings
- `EmbeddingProvider` built-in: OpenAI (`text-embedding-3-small`), AWS Bedrock (Titan)
- `VectorBackend` ABC — astrazione per storage e ricerca vettoriale
- `VectorBackend` built-in: SQLite (brute-force cosine, dev), pgvector (prod)
- Pipeline auto: su `insert` / `update` → genera embedding → salva in vector store
- Tool auto-generati: `semantic_search_{resource}(query, limit)` per ogni modello con campi embedding
- Endpoint REST: `POST /{resource}/search` per semantic search diretta (senza agent)
- Integrazione agent: `@agent` vede automaticamente sia CRUD tools che semantic tools
- Cross-table reasoning: agent multi-model con accesso a semantic search su tutti i modelli
- Settings: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `VECTOR_BACKEND`

Cosa NON è incluso in V3:
- Streaming LLM response (V4)
- Conversation history persistente (V4)
- Hooks before/after (V4)
- Auth/permissions (V4)
- Step Functions / orchestrazione async (V4)
- FAISS, Pinecone, Weaviate o vector DB esterni
- Embedding multimodali (immagini, audio)

---

## Analisi Critica del Design

### Perché questo è il passo naturale

Ragin evolve da:

```
V1:  Model → CRUD
V2:  Model → CRUD + Agent
V3:  Model → CRUD + Agent + Semantic Layer
```

Con V3, ragin diventa un **AI-native backend con knowledge layer**: il modello non
è più solo una tabella SQL, ma un'entità con comprensione semantica.

### Decisioni architetturali chiave

**1. Tool locali, NON via HTTP.**
Come in V2, i tool semantici chiamano il vector backend direttamente in-process.
L'agente non fa HTTP call a se stesso — chiama `_make_semantic_caller()` che
accede al `VectorBackend` locale. Più veloce, meno costi, zero overhead di rete.

**2. Pipeline sync, non async.**
L'embedding viene generato inline su insert/update. Per un campo di testo tipico
(< 8K token), la chiamata OpenAI embeddings impiega ~50-100ms. Accettabile per
la stragrande maggioranza dei casi. Una pipeline async (SQS / EventBridge)
aggiungerebbe complessità enorme per un guadagno marginale in V3.

**3. SQLite brute-force per dev, pgvector per prod.**
- Dev: embeddings salvati come JSON blob in una tabella SQLite dedicata. Ricerca
  via cosine similarity in-memory con `numpy`. Funziona benissimo fino a ~10K record.
  Nessuna extension da installare.
- Prod: pgvector su PostgreSQL. Query native `ORDER BY embedding <=> query_vector`.
  Già produzione-ready, supportato da tutti i cloud.
- Scartato: `sqlite-vss` / `sqlite-vec` — extension instabili, difficili da installare
  in Lambda. Il brute-force è più semplice e sufficiente per dev.
- Scartato: FAISS — dipendenza pesante, non serve quando pgvector è disponibile.

**4. `VECTOR_BACKEND = "auto"` come default.**
Se `DATABASE_URL` è PostgreSQL → usa pgvector. Altrimenti → SQLite brute-force.
Nessuna configurazione manuale per il caso comune.

**5. Un embedding per riga, non per campo.**
Anche se più campi sono `embedding=True`, viene generato un **unico embedding per record**
concatenando i valori dei campi marcati. Motivo: riduce i costi API, semplifica la ricerca,
e il vector store ha una sola colonna embedding per tabella.

---

## Struttura File Aggiunti in V3

```
ragin/
  # ... tutto V1 + V2 invariato ...

  embeddings/
    __init__.py              # export EmbeddingProvider classes, lazy
    base.py                  # BaseEmbeddingProvider ABC
    openai.py                # OpenAIEmbeddingProvider
    bedrock.py               # BedrockEmbeddingProvider

  vector/
    __init__.py              # configure_vector_backend(), get_vector_backend()
    base.py                  # BaseVectorBackend ABC
    sqlite.py                # SQLiteVectorBackend (dev: brute-force cosine)
    pgvector.py              # PgVectorBackend (prod: pgvector extension)

  # Modifiche a file esistenti:
  core/fields.py             # Field() accetta embedding=True
  agent/tools.py             # build_crud_tools() + build_semantic_tools()
  agent/decorator.py         # @agent include automaticamente semantic tools
  resource/crud.py           # CrudHandlerFactory hooks per embedding pipeline
  persistence/schema.py      # tabella vettoriale generata da schema
  cli/builder.py             # entry point aggiornato
  conf/settings.py           # nuovi default: EMBEDDING_PROVIDER, ecc.
```

### Nuove dipendenze

```toml
[project.optional-dependencies]
# ... V1 + V2 invariate ...
embeddings-openai = ["openai>=1.0"]        # condivide con providers.openai
embeddings-bedrock = ["boto3>=1.34"]       # condivide con providers.bedrock
pgvector = ["pgvector>=0.3"]               # pgvector Python binding
```

Nota: `numpy` diventa una dipendenza **core** (necessaria per cosine similarity
nel backend SQLite e per manipolazione vettori). È leggera (~30MB) e già
presente in quasi tutti gli ambienti Python.

```toml
[project]
dependencies = [
    # ... dipendenze V1 esistenti ...
    "numpy>=1.26",
]
```

---

## 1. `Field(embedding=True)`

### 1.1 Aggiornamento a `Field()`

Il `Field()` di ragin accetta un nuovo parametro `embedding`:

```python
# ragin/core/fields.py  (aggiornamento)

def Field(
    default=...,
    *,
    primary_key: bool = False,
    nullable: bool = True,
    unique: bool = False,
    index: bool = False,
    description: str = None,
    embedding: bool = False,     # NEW V3
    **kwargs,
) -> Any:
    ragin_meta = {
        "primary_key": primary_key,
        "nullable": nullable,
        "unique": unique,
        "index": index,
        "embedding": embedding,    # NEW V3
    }
    return pydantic.Field(
        default,
        json_schema_extra={"ragin": ragin_meta},
        description=description,
        **kwargs,
    )
```

### 1.2 Helper per leggere i campi embedding

```python
# ragin/core/fields.py  (aggiunta)

def get_embedding_fields(model_cls: type) -> list[str]:
    """Ritorna i nomi dei campi con embedding=True."""
    fields = []
    for name in model_cls.model_fields:
        meta = get_ragin_meta(model_cls, name)
        if meta.get("embedding"):
            fields.append(name)
    return fields


def has_embeddings(model_cls: type) -> bool:
    """True se il modello ha almeno un campo con embedding=True."""
    return len(get_embedding_fields(model_cls)) > 0
```

### 1.3 Uso nel modello

```python
from ragin import Model, Field, resource

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str
    bio: str = Field(embedding=True, description="Short biography of the user")
    skills: str = Field(embedding=True, description="Comma-separated list of skills")
```

`bio` e `skills` sono concatenati in un singolo testo di embedding:
`"Short biography of the user: {bio}\nComma-separated list of skills: {skills}"`

---

## 2. EmbeddingProvider

### 2.1 Base class

```python
# ragin/embeddings/base.py

from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    """
    Interfaccia per generare embeddings da testo.
    Ogni provider wrappa un servizio di embeddings esterno.
    """

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """
        Genera un embedding vector da un testo.
        Ritorna una lista di float (dimensioni dipendono dal modello).
        """
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Genera embeddings per più testi in un singolo API call.
        Più efficiente di chiamare embed() N volte.
        """
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimensioni del vettore di embedding."""
        ...
```

### 2.2 OpenAI Embedding Provider

```python
# ragin/embeddings/openai.py

from ragin.embeddings.base import BaseEmbeddingProvider


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Usa OpenAI Embeddings API (text-embedding-3-small, text-embedding-3-large)."""

    DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None):
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

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS.get(self.model, 1536)

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]
```

### 2.3 Bedrock Embedding Provider

```python
# ragin/embeddings/bedrock.py

import json
from ragin.embeddings.base import BaseEmbeddingProvider


class BedrockEmbeddingProvider(BaseEmbeddingProvider):
    """Usa AWS Bedrock Titan Embeddings."""

    DIMENSIONS = {
        "amazon.titan-embed-text-v2:0": 1024,
        "amazon.titan-embed-text-v1": 1536,
    }

    def __init__(
        self,
        model_id: str = "amazon.titan-embed-text-v2:0",
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

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS.get(self.model_id, 1024)

    def embed(self, text: str) -> list[float]:
        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps({"inputText": text}),
        )
        result = json.loads(response["body"].read())
        return result["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Bedrock Titan non supporta batch nativo — chiamate sequenziali
        return [self.embed(text) for text in texts]
```

### 2.4 Lazy exports

```python
# ragin/embeddings/__init__.py

from ragin.embeddings.base import BaseEmbeddingProvider

__all__ = ["BaseEmbeddingProvider"]

_provider_instance: BaseEmbeddingProvider | None = None


def get_embedding_provider() -> BaseEmbeddingProvider | None:
    """
    Ritorna il provider di embeddings configurato, o None se non configurato.
    Lazy: crea l'istanza al primo accesso.
    """
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    from ragin.conf import settings
    provider_name = getattr(settings, "EMBEDDING_PROVIDER", "none")

    if provider_name == "none" or not provider_name:
        return None
    elif provider_name == "openai":
        from ragin.embeddings.openai import OpenAIEmbeddingProvider
        model = getattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")
        _provider_instance = OpenAIEmbeddingProvider(model=model)
    elif provider_name == "bedrock":
        from ragin.embeddings.bedrock import BedrockEmbeddingProvider
        model_id = getattr(settings, "EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
        region = getattr(settings, "EMBEDDING_REGION", "us-east-1")
        _provider_instance = BedrockEmbeddingProvider(model_id=model_id, region=region)
    else:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider_name}")

    return _provider_instance


def reset_embedding_provider():
    """Reset per test."""
    global _provider_instance
    _provider_instance = None


def __getattr__(name):
    if name == "OpenAIEmbeddingProvider":
        from ragin.embeddings.openai import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider
    if name == "BedrockEmbeddingProvider":
        from ragin.embeddings.bedrock import BedrockEmbeddingProvider
        return BedrockEmbeddingProvider
    raise AttributeError(f"module 'ragin.embeddings' has no attribute {name}")
```

---

## 3. VectorBackend

### 3.1 Base class

```python
# ragin/vector/base.py

from abc import ABC, abstractmethod


class BaseVectorBackend(ABC):
    """
    Interfaccia per storage e ricerca di embeddings.
    Ogni modello con campi embedding ha una "tabella vettoriale" associata.
    """

    @abstractmethod
    def ensure_table(self, model_cls: type, dimensions: int) -> None:
        """
        Crea la tabella vettoriale per il modello se non esiste.
        Chiamato una volta al primo accesso.
        """
        ...

    @abstractmethod
    def upsert(self, model_cls: type, pk_value: str, embedding: list[float], text: str) -> None:
        """
        Inserisce o aggiorna un embedding per un record specifico.
        - pk_value: valore della primary key del record
        - embedding: vettore di embedding
        - text: testo originale concatenato (per debug/ispezione)
        """
        ...

    @abstractmethod
    def search(
        self,
        model_cls: type,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[dict]:
        """
        Cerca i record più simili al query_embedding.
        Ritorna una lista di dict con:
        - pk: valore primary key
        - score: similarità coseno (0-1, 1 = identico)
        - text: testo originale
        """
        ...

    @abstractmethod
    def delete(self, model_cls: type, pk_value: str) -> None:
        """Rimuove l'embedding di un record (es. dopo DELETE del record)."""
        ...
```

### 3.2 SQLiteVectorBackend (dev)

Approccio: tabella SQLite con embedding serializzato come JSON blob.
Ricerca via brute-force cosine similarity con numpy. Funziona fino a ~10K record
per modello senza problemi di performance.

```python
# ragin/vector/sqlite.py

import json
import numpy as np
import sqlalchemy as sa
from ragin.vector.base import BaseVectorBackend


class SQLiteVectorBackend(BaseVectorBackend):
    """
    Backend vettoriale per SQLite.
    Salva embeddings come JSON blob, ricerca con cosine similarity brute-force.
    Ideale per sviluppo locale.
    """

    def __init__(self, engine: sa.Engine):
        self._engine = engine
        self._metadata = sa.MetaData()
        self._tables: dict[str, sa.Table] = {}

    def _table_name(self, model_cls: type) -> str:
        return f"{model_cls.ragin_table_name()}_embeddings"

    def ensure_table(self, model_cls: type, dimensions: int) -> None:
        name = self._table_name(model_cls)
        if name in self._tables:
            return

        table = sa.Table(
            name,
            self._metadata,
            sa.Column("pk", sa.String, primary_key=True),
            sa.Column("embedding", sa.Text),       # JSON serialized float array
            sa.Column("text", sa.Text),             # testo originale
            sa.Column("dimensions", sa.Integer),
        )
        self._tables[name] = table
        self._metadata.create_all(self._engine)

    def upsert(self, model_cls: type, pk_value: str, embedding: list[float], text: str) -> None:
        name = self._table_name(model_cls)
        table = self._tables[name]
        emb_json = json.dumps(embedding)

        with self._engine.connect() as conn:
            # Try update first, then insert
            stmt = sa.update(table).where(table.c.pk == str(pk_value)).values(
                embedding=emb_json, text=text, dimensions=len(embedding)
            )
            result = conn.execute(stmt)
            if result.rowcount == 0:
                conn.execute(table.insert().values(
                    pk=str(pk_value), embedding=emb_json,
                    text=text, dimensions=len(embedding),
                ))
            conn.commit()

    def search(
        self,
        model_cls: type,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[dict]:
        name = self._table_name(model_cls)
        table = self._tables[name]
        query_vec = np.array(query_embedding, dtype=np.float32)

        with self._engine.connect() as conn:
            rows = conn.execute(sa.select(table)).fetchall()

        results = []
        for row in rows:
            row_dict = dict(row._mapping)
            stored_vec = np.array(json.loads(row_dict["embedding"]), dtype=np.float32)
            score = _cosine_similarity(query_vec, stored_vec)
            results.append({
                "pk": row_dict["pk"],
                "score": float(score),
                "text": row_dict["text"],
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def delete(self, model_cls: type, pk_value: str) -> None:
        name = self._table_name(model_cls)
        table = self._tables[name]
        with self._engine.connect() as conn:
            conn.execute(sa.delete(table).where(table.c.pk == str(pk_value)))
            conn.commit()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity tra due vettori."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return dot / norm
```

### 3.3 PgVectorBackend (prod)

Usa l'extension `pgvector` di PostgreSQL per ricerca vettoriale nativa.

```python
# ragin/vector/pgvector.py

import json
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from ragin.vector.base import BaseVectorBackend


class PgVectorBackend(BaseVectorBackend):
    """
    Backend vettoriale per PostgreSQL con pgvector.
    Usa il tipo VECTOR nativo e l'operatore <=> per cosine distance.
    """

    def __init__(self, engine: sa.Engine):
        self._engine = engine
        self._metadata = sa.MetaData()
        self._tables: dict[str, sa.Table] = {}
        self._ensure_extension()

    def _ensure_extension(self):
        """Crea l'extension pgvector se non esiste."""
        with self._engine.connect() as conn:
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

    def _table_name(self, model_cls: type) -> str:
        return f"{model_cls.ragin_table_name()}_embeddings"

    def ensure_table(self, model_cls: type, dimensions: int) -> None:
        name = self._table_name(model_cls)
        if name in self._tables:
            return

        table = sa.Table(
            name,
            self._metadata,
            sa.Column("pk", sa.String, primary_key=True),
            sa.Column("embedding", Vector(dimensions)),
            sa.Column("text", sa.Text),
        )
        self._tables[name] = table
        self._metadata.create_all(self._engine)

    def upsert(self, model_cls: type, pk_value: str, embedding: list[float], text: str) -> None:
        name = self._table_name(model_cls)
        table = self._tables[name]

        with self._engine.connect() as conn:
            # PostgreSQL UPSERT via ON CONFLICT
            stmt = sa.dialects.postgresql.insert(table).values(
                pk=str(pk_value), embedding=embedding, text=text,
            ).on_conflict_do_update(
                index_elements=["pk"],
                set_={"embedding": embedding, "text": text},
            )
            conn.execute(stmt)
            conn.commit()

    def search(
        self,
        model_cls: type,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[dict]:
        name = self._table_name(model_cls)
        table = self._tables[name]

        # pgvector: <=> è cosine distance (1 - similarity), quindi ordine ASC
        distance = table.c.embedding.cosine_distance(query_embedding)
        query = (
            sa.select(table.c.pk, table.c.text, (1 - distance).label("score"))
            .order_by(distance)
            .limit(limit)
        )

        with self._engine.connect() as conn:
            rows = conn.execute(query).fetchall()

        return [
            {"pk": row.pk, "score": float(row.score), "text": row.text}
            for row in rows
        ]

    def delete(self, model_cls: type, pk_value: str) -> None:
        name = self._table_name(model_cls)
        table = self._tables[name]
        with self._engine.connect() as conn:
            conn.execute(sa.delete(table).where(table.c.pk == str(pk_value)))
            conn.commit()
```

### 3.4 Backend auto-detection e configurazione

```python
# ragin/vector/__init__.py

from ragin.vector.base import BaseVectorBackend

_backend: BaseVectorBackend | None = None


def configure_vector_backend(engine=None, backend: str = "auto") -> BaseVectorBackend | None:
    """
    Configura il vector backend.
    - "auto": pgvector se DB è PostgreSQL, sqlite se DB è SQLite
    - "sqlite": forza SQLiteVectorBackend
    - "pgvector": forza PgVectorBackend
    - "none": disabilita vector backend
    """
    global _backend

    if backend == "none":
        _backend = None
        return None

    if engine is None:
        from ragin.persistence import get_backend
        engine = get_backend()._engine

    db_url = str(engine.url)

    if backend == "auto":
        if "postgresql" in db_url:
            backend = "pgvector"
        else:
            backend = "sqlite"

    if backend == "pgvector":
        from ragin.vector.pgvector import PgVectorBackend
        _backend = PgVectorBackend(engine)
    elif backend == "sqlite":
        from ragin.vector.sqlite import SQLiteVectorBackend
        _backend = SQLiteVectorBackend(engine)
    else:
        raise ValueError(f"Unknown VECTOR_BACKEND: {backend}")

    return _backend


def get_vector_backend() -> BaseVectorBackend | None:
    """Ritorna il vector backend configurato, o None se nessun modello ha embeddings."""
    global _backend
    if _backend is None:
        from ragin.conf import settings
        backend = getattr(settings, "VECTOR_BACKEND", "auto")
        if backend == "none":
            return None
        configure_vector_backend(backend=backend)
    return _backend


def reset_vector_backend():
    """Reset per test."""
    global _backend
    _backend = None
```

---

## 4. Embedding Pipeline

### 4.1 Testo di embedding

Per ogni record, i campi `embedding=True` sono concatenati in un singolo testo:

```python
# ragin/embeddings/pipeline.py

from ragin.core.fields import get_embedding_fields, get_ragin_meta


def build_embedding_text(model_cls: type, data: dict) -> str | None:
    """
    Costruisce il testo da embeddare concatenando i campi con embedding=True.
    Ritorna None se nessun campo embedding ha un valore.

    Formato: "{field_description}: {value}\n{field_description}: {value}"
    Se il campo non ha description, usa il nome del campo.
    """
    fields = get_embedding_fields(model_cls)
    if not fields:
        return None

    parts = []
    for field_name in fields:
        value = data.get(field_name)
        if value is None or value == "":
            continue
        field_info = model_cls.model_fields[field_name]
        label = field_info.description or field_name
        parts.append(f"{label}: {value}")

    return "\n".join(parts) if parts else None


def generate_and_store_embedding(model_cls: type, pk_value: str, data: dict) -> None:
    """
    Genera l'embedding per un record e lo salva nel vector store.
    Chiamato automaticamente da create_handler e update_handler.
    No-op se:
      - il modello non ha campi embedding
      - nessun embedding provider è configurato
      - nessun campo embedding ha un valore
    """
    from ragin.core.fields import has_embeddings
    if not has_embeddings(model_cls):
        return

    from ragin.embeddings import get_embedding_provider
    provider = get_embedding_provider()
    if provider is None:
        return

    text = build_embedding_text(model_cls, data)
    if text is None:
        return

    from ragin.vector import get_vector_backend
    backend = get_vector_backend()
    if backend is None:
        return

    backend.ensure_table(model_cls, provider.dimensions)
    embedding = provider.embed(text)
    backend.upsert(model_cls, pk_value, embedding, text)


def delete_embedding(model_cls: type, pk_value: str) -> None:
    """
    Rimuove l'embedding di un record dal vector store.
    Chiamato automaticamente da delete_handler.
    """
    from ragin.core.fields import has_embeddings
    if not has_embeddings(model_cls):
        return

    from ragin.vector import get_vector_backend
    backend = get_vector_backend()
    if backend is None:
        return

    backend.delete(model_cls, pk_value)
```

### 4.2 Integrazione con CRUD handlers

I CRUD handler esistenti vengono estesi per chiamare la pipeline automaticamente:

```python
# ragin/resource/crud.py  — modifiche

class CrudHandlerFactory:

    def create_handler(self):
        model_cls = self.model_cls
        def handler(request: InternalRequest) -> InternalResponse:
            # ... validazione e insert esistenti (invariato) ...
            try:
                data = model_cls.model_validate(request.json_body)
            except ValidationError as exc:
                return InternalResponse.bad_request(exc.errors())
            try:
                record = get_backend().insert(model_cls, data.model_dump())
            except IntegrityError:
                return InternalResponse.conflict("Resource with that key already exists.")

            # NEW V3: genera embedding
            from ragin.embeddings.pipeline import generate_and_store_embedding
            pk_field = model_cls.primary_key_field()
            generate_and_store_embedding(model_cls, record[pk_field], record)

            return InternalResponse.created(record)
        return handler

    def update_handler(self):
        model_cls = self.model_cls
        def handler(request: InternalRequest) -> InternalResponse:
            pk = request.path_params["id"]
            data = request.json_body
            backend = get_backend()
            record = backend.update(model_cls, pk, data)
            if record is None:
                return InternalResponse.not_found()

            # NEW V3: rigenera embedding (il record completo con i nuovi valori)
            from ragin.embeddings.pipeline import generate_and_store_embedding
            generate_and_store_embedding(model_cls, pk, record)

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

            # NEW V3: rimuovi embedding
            from ragin.embeddings.pipeline import delete_embedding
            delete_embedding(model_cls, pk)

            return InternalResponse.no_content()
        return handler
```

La pipeline è **completamente trasparente**: se il modello non ha campi embedding
o nessun provider è configurato, le funzioni sono no-op. Zero overhead per chi
non usa V3.

---

## 5. Semantic Search Tools

### 5.1 Tool auto-generati

Per ogni modello con almeno un campo `embedding=True`, viene generato un tool
`semantic_search_{resource}`:

```python
# ragin/agent/tools.py  — aggiunta

def build_semantic_tools(model_cls: type) -> list[ToolDefinition]:
    """
    Genera tool di semantic search per un modello con campi embedding.
    Ritorna lista vuota se il modello non ha campi embedding.
    """
    from ragin.core.fields import has_embeddings
    if not has_embeddings(model_cls):
        return []

    resource_name = model_cls.__name__.lower() + "s"
    singular = model_cls.__name__.lower()

    return [ToolDefinition(
        name=f"semantic_search_{resource_name}",
        description=(
            f"Search {resource_name} by meaning using semantic similarity. "
            f"Use when the user asks to find {resource_name} based on concepts, "
            f"topics, or natural language descriptions rather than exact field values."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum number of results to return",
                },
            },
            "required": ["query"],
        },
        handler=_make_semantic_caller(model_cls),
        model=model_cls,
    )]


def _make_semantic_caller(model_cls: type):
    """
    Crea l'handler per il tool di semantic search.
    L'handler:
      1. Genera l'embedding della query
      2. Cerca nel vector store
      3. Recupera i record completi dal SQL backend
      4. Ritorna i risultati con score
    """
    def tool_handler(arguments: dict) -> dict:
        from ragin.embeddings import get_embedding_provider
        from ragin.vector import get_vector_backend
        from ragin.persistence import get_backend

        query = arguments.get("query", "")
        limit = arguments.get("limit", 5)

        provider = get_embedding_provider()
        if provider is None:
            return {"error": "No embedding provider configured"}

        vector_backend = get_vector_backend()
        if vector_backend is None:
            return {"error": "No vector backend configured"}

        # Genera embedding della query
        query_embedding = provider.embed(query)

        # Cerca nel vector store
        results = vector_backend.search(model_cls, query_embedding, limit=limit)

        # Arricchisci con i record completi dal DB
        backend = get_backend()
        enriched = []
        for r in results:
            record = backend.get(model_cls, r["pk"])
            if record is not None:
                enriched.append({
                    **record,
                    "_score": r["score"],
                })

        return {"results": enriched, "count": len(enriched)}

    return tool_handler
```

### 5.2 Endpoint REST per semantic search diretta

Oltre al tool per l'agent, ragin genera un endpoint REST per la semantic search
direttamente accessibile via HTTP, senza passare dall'agent:

```python
# ragin/resource/decorator.py  — aggiunta in @resource

# Dentro @resource, dopo aver registrato le route CRUD:
if has_embeddings(model_cls):
    from ragin.agent.tools import build_semantic_tools
    semantic_tools = build_semantic_tools(model_cls)
    if semantic_tools:
        search_tool = semantic_tools[0]

        def _make_search_handler(tool=search_tool):
            def handler(request):
                body = request.json_body
                result = tool.handler(body)
                return InternalResponse.ok(result)
            return handler

        registry.register_route(RouteDefinition(
            method="POST",
            path=f"{base_path}/search",
            handler=_make_search_handler(),
            model=model_cls,
            operation="semantic_search",
        ))
```

Risultato:

```bash
# Semantic search via REST (senza agent)
curl -X POST http://localhost:8000/users/search \
  -H "Content-Type: application/json" \
  -d '{"query": "people who know Python", "limit": 5}'
```

```json
{
  "results": [
    {"id": "u1", "name": "Alice", "bio": "Python developer...", "_score": 0.92},
    {"id": "u3", "name": "Bob", "bio": "Backend engineer...", "_score": 0.85}
  ],
  "count": 2
}
```

---

## 6. Integrazione Agent

### 6.1 @agent include automaticamente i semantic tools

Il decorator `@agent` in V3 rileva automaticamente i modelli con campi embedding
e aggiunge i tool semantici accanto ai CRUD tools:

```python
# ragin/agent/decorator.py  — modifica

def _resolve_tools(models, tools_config):
    """Risolve la configurazione tools in una lista di ToolDefinition."""
    all_tools = []
    for m in models:
        if tools_config == ["crud"] or "crud" in tools_config:
            all_tools.extend(build_crud_tools(m))
        else:
            for op in tools_config:
                all_tools.extend(build_crud_tools(m, operations=[op]))

        # NEW V3: aggiungi semantic tools se il modello ha embeddings
        all_tools.extend(build_semantic_tools(m))

    return all_tools
```

### 6.2 System prompt aggiornato

Il system prompt in V3 menziona la capacità di semantic search:

```python
# ragin/agent/prompt.py  — modifica

def generate_system_prompt(models: list[type], description: str = "") -> str:
    # ... generazione esistente ...

    # NEW V3: aggiungi istruzioni per semantic search
    embedding_models = [m for m in models if has_embeddings(m)]
    if embedding_models:
        parts.append("\n## Semantic Search")
        parts.append("Some models support semantic search. Use semantic_search_* tools when:")
        parts.append("- The user asks to find records by meaning, concepts, or topics")
        parts.append("- The user's query is natural language, not exact field values")
        parts.append("- You need to find similar or related records")
        parts.append("Use regular CRUD list/filter tools when the user wants exact matches.\n")

    parts.append("Use the available tools to perform operations on these models.")
    parts.append("Always confirm actions with a clear response to the user.")

    return "\n".join(parts)
```

### 6.3 Esempio completo — cross-table reasoning

```python
from ragin import ServerlessApp, Model, Field, resource, agent
from ragin.providers import OpenAIProvider

app = ServerlessApp()

@resource(operations=["crud"])
class User(Model):
    id: str = Field(primary_key=True)
    name: str
    email: str
    bio: str = Field(embedding=True, description="Short biography")
    skills: str = Field(embedding=True, description="Skills and expertise")

@resource(operations=["crud"])
class Task(Model):
    id: str = Field(primary_key=True)
    title: str
    description: str = Field(embedding=True, description="Task description")
    assignee: str = Field(description="User ID of the assignee")
    status: str = "open"

@agent(
    model=[User, Task],
    provider=OpenAIProvider(model="gpt-4o"),
    description="Project assistant. Manages users and tasks. Can find people by skills and match them to tasks.",
)
class ProjectAgent:
    pass
```

Tool disponibili per l'agent:

| Tool | Tipo | Descrizione |
|------|------|-------------|
| `create_user` | CRUD | Crea un nuovo user |
| `list_users` | CRUD | Lista users con filtri esatti |
| `get_user` | CRUD | Recupera user per ID |
| `update_user` | CRUD | Aggiorna user |
| `delete_user` | CRUD | Elimina user |
| `semantic_search_users` | Semantic | Cerca users per significato |
| `create_task` | CRUD | Crea un nuovo task |
| `list_tasks` | CRUD | Lista tasks con filtri esatti |
| `get_task` | CRUD | Recupera task per ID |
| `update_task` | CRUD | Aggiorna task |
| `delete_task` | CRUD | Elimina task |
| `semantic_search_tasks` | Semantic | Cerca tasks per significato |

Conversazione esempio:

```
User: "Find someone who knows machine learning and assign them to the NLP task"

Agent:
  1. semantic_search_users(query="machine learning expertise")
     → [{"id": "u3", "name": "Alice", "skills": "ML, Python, NLP", "_score": 0.94}]
  2. semantic_search_tasks(query="NLP task")
     → [{"id": "t7", "title": "Build NLP pipeline", "_score": 0.91}]
  3. update_task(id="t7", assignee="u3")
     → {"id": "t7", "assignee": "u3", ...}
  Response: "I found Alice (ML, Python, NLP expertise) and assigned her to 'Build NLP pipeline'."
```

L'agente decide **autonomamente** quando usare semantic search vs CRUD list.
Se l'utente dice "show me all tasks assigned to u3" → usa `list_tasks(assignee="u3")`.
Se dice "find tasks about data processing" → usa `semantic_search_tasks(query="data processing")`.

---

## 7. Settings V3

### 7.1 Nuove impostazioni

```python
# ragin/conf/settings.py  — aggiornamenti

_DEFAULTS = {
    # ... V1 esistenti ...
    "DATABASE_URL": "sqlite:///./ragin_dev.db",
    "PROVIDER": "local",
    "DEBUG": True,
    "HOST": "127.0.0.1",
    "PORT": 8000,
    "APP": "main:app",

    # NEW V3
    "EMBEDDING_PROVIDER": "none",                      # "none" | "openai" | "bedrock"
    "EMBEDDING_MODEL": "text-embedding-3-small",       # modello specifico del provider
    "EMBEDDING_REGION": "us-east-1",                   # per Bedrock
    "VECTOR_BACKEND": "auto",                          # "auto" | "sqlite" | "pgvector" | "none"
}
```

### 7.2 Configurazione per ambiente

```python
# settings.py (progetto utente — sviluppo)

DATABASE_URL = "sqlite:///./ragin_dev.db"
EMBEDDING_PROVIDER = "openai"
EMBEDDING_MODEL = "text-embedding-3-small"
# VECTOR_BACKEND = "auto"  →  rileva SQLite automaticamente
```

```python
# settings.py (progetto utente — produzione)

DATABASE_URL = "postgresql+psycopg2://user:pwd@host:5432/mydb"
EMBEDDING_PROVIDER = "openai"
EMBEDDING_MODEL = "text-embedding-3-small"
# VECTOR_BACKEND = "auto"  →  rileva PostgreSQL, usa pgvector
```

Override via env var:

```bash
RAGIN_EMBEDDING_PROVIDER=bedrock
RAGIN_EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
RAGIN_EMBEDDING_REGION=us-east-1
```

---

## 8. Serverless — Come Funziona

### 8.1 Concetto fondamentale: tutto è stateless

L'agente NON è persistente. Ogni richiesta:

```
API Gateway → Lambda
  │
  ├── 1. Carica contesto (tools, system prompt)
  ├── 2. Chiama LLM con il messaggio
  ├── 3. LLM ritorna tool_call (es. semantic_search_users)
  ├── 4. Esegue tool localmente:
  │      ├── genera embedding della query (OpenAI API call ~50ms)
  │      └── cerca nel vector store (pgvector query ~10ms)
  ├── 5. Reinvia risultati al LLM
  ├── 6. LLM genera risposta finale
  └── 7. Ritorna al client
```

Tutto stateless lato compute. Lo stato è nel DB (SQL + vector store).

### 8.2 Latenza

| Operazione | Latenza tipica |
|-----------|---------------|
| CRUD senza embedding | ~50ms (invariato da V1) |
| CRUD con embedding (insert) | ~150ms (+100ms per API embedding) |
| Semantic search (via agent) | ~500ms (LLM + embedding query + vector search) |
| Semantic search (REST diretto) | ~150ms (embedding query + vector search, no LLM) |

Il bottleneck è la chiamata LLM, non il vector search. Per chi vuole performance
senza LLM overhead, l'endpoint `POST /{resource}/search` è la scelta giusta.

---

## 9. Aggiornamenti al Build

`ragin build` in V3 genera entry point aggiornati che includono la configurazione
del vector backend:

```python
# build/_ragin_entry.py  — aggiornamento V3

# Se ci sono modelli con embedding, il vector backend va inizializzato
from ragin.vector import configure_vector_backend
configure_vector_backend()
```

Il `routes.json` include le nuove route:

```json
{
  "provider": "aws",
  "lambdas": {
    "crud": {
      "entry_point": "_ragin_entry",
      "routes": [
        {"method": "POST",   "path": "/users"},
        {"method": "GET",    "path": "/users"},
        {"method": "GET",    "path": "/users/{id}"},
        {"method": "PATCH",  "path": "/users/{id}"},
        {"method": "DELETE", "path": "/users/{id}"},
        {"method": "POST",   "path": "/users/search"}
      ]
    },
    "agent": {
      "entry_point": "_ragin_entry",
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

## 10. MCP Server — Aggiornamento V3

Il MCP server espone automaticamente anche i tool semantici:

```python
# build/_ragin_mcp_entry.py  — aggiornamento V3

from ragin.agent.tools import build_crud_tools, build_semantic_tools

all_tools = []
for model_cls in registry._models.values():
    all_tools.extend(build_crud_tools(model_cls))
    all_tools.extend(build_semantic_tools(model_cls))  # NEW V3

mcp = MCPServer(all_tools)
```

MCP `tools/list` ritorna anche i tool semantici:

```json
{
  "tools": [
    {"name": "create_user", "description": "Create a new user.", ...},
    {"name": "list_users", "description": "List users...", ...},
    {"name": "semantic_search_users", "description": "Search users by meaning...", ...}
  ]
}
```

Questo significa che **Claude Desktop, Cursor, VS Code** e qualsiasi client MCP
possono fare semantic search sui tuoi dati via MCP.

---

## 11. Test Plan

### 11.1 Test Embedding Pipeline

```python
# tests/test_embedding_pipeline.py

from unittest.mock import MagicMock
from ragin import Model, Field, resource
from ragin.embeddings.pipeline import build_embedding_text, generate_and_store_embedding


class MockEmbeddingProvider:
    dimensions = 3

    def embed(self, text):
        return [0.1, 0.2, 0.3]

    def embed_batch(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_build_embedding_text():
    class User(Model):
        id: str = Field(primary_key=True)
        name: str
        bio: str = Field(embedding=True, description="Biography")
        skills: str = Field(embedding=True, description="Skills")

    text = build_embedding_text(User, {"id": "u1", "name": "Alice", "bio": "Loves Python", "skills": "ML, API"})
    assert "Biography: Loves Python" in text
    assert "Skills: ML, API" in text


def test_build_embedding_text_no_embedding_fields():
    class User(Model):
        id: str = Field(primary_key=True)
        name: str

    text = build_embedding_text(User, {"id": "u1", "name": "Alice"})
    assert text is None


def test_generate_and_store_no_provider():
    """Se nessun provider è configurato, è un no-op."""
    class User(Model):
        id: str = Field(primary_key=True)
        bio: str = Field(embedding=True)

    # Non dovrebbe lanciare eccezioni
    generate_and_store_embedding(User, "u1", {"id": "u1", "bio": "test"})
```

### 11.2 Test VectorBackend SQLite

```python
# tests/test_vector_sqlite.py

import sqlalchemy as sa
from ragin import Model, Field
from ragin.vector.sqlite import SQLiteVectorBackend


def test_upsert_and_search():
    engine = sa.create_engine("sqlite:///:memory:")

    class User(Model):
        id: str = Field(primary_key=True)
        bio: str = Field(embedding=True)

    backend = SQLiteVectorBackend(engine)
    backend.ensure_table(User, dimensions=3)

    backend.upsert(User, "u1", [1.0, 0.0, 0.0], "Python developer")
    backend.upsert(User, "u2", [0.0, 1.0, 0.0], "Java developer")
    backend.upsert(User, "u3", [0.9, 0.1, 0.0], "Python and ML engineer")

    results = backend.search(User, [1.0, 0.0, 0.0], limit=2)
    assert len(results) == 2
    assert results[0]["pk"] == "u1"  # most similar
    assert results[0]["score"] > results[1]["score"]


def test_delete():
    engine = sa.create_engine("sqlite:///:memory:")

    class User(Model):
        id: str = Field(primary_key=True)
        bio: str = Field(embedding=True)

    backend = SQLiteVectorBackend(engine)
    backend.ensure_table(User, dimensions=3)

    backend.upsert(User, "u1", [1.0, 0.0, 0.0], "test")
    backend.delete(User, "u1")

    results = backend.search(User, [1.0, 0.0, 0.0], limit=10)
    assert len(results) == 0


def test_upsert_overwrites():
    engine = sa.create_engine("sqlite:///:memory:")

    class User(Model):
        id: str = Field(primary_key=True)
        bio: str = Field(embedding=True)

    backend = SQLiteVectorBackend(engine)
    backend.ensure_table(User, dimensions=3)

    backend.upsert(User, "u1", [1.0, 0.0, 0.0], "Old text")
    backend.upsert(User, "u1", [0.0, 1.0, 0.0], "New text")

    results = backend.search(User, [0.0, 1.0, 0.0], limit=1)
    assert results[0]["pk"] == "u1"
    assert results[0]["text"] == "New text"
```

### 11.3 Test Semantic Tools

```python
# tests/test_semantic_tools.py

from ragin import Model, Field, resource
from ragin.agent.tools import build_semantic_tools


def test_semantic_tools_generated():
    @resource(operations=["crud"])
    class User(Model):
        id: str = Field(primary_key=True)
        bio: str = Field(embedding=True)

    tools = build_semantic_tools(User)
    assert len(tools) == 1
    assert tools[0].name == "semantic_search_users"
    assert "query" in tools[0].parameters["properties"]


def test_no_semantic_tools_without_embedding():
    @resource(operations=["crud"])
    class User(Model):
        id: str = Field(primary_key=True)
        name: str

    tools = build_semantic_tools(User)
    assert tools == []
```

### 11.4 Test Agent con Semantic Tools

```python
# tests/test_agent_semantic.py

from ragin import Model, Field, resource, agent
from ragin.providers.base import BaseProvider, AgentResponse, ToolCall


class MockProvider(BaseProvider):
    def __init__(self, responses):
        self._responses = iter(responses)

    def complete(self, messages, tools=None):
        return next(self._responses)


def test_agent_has_semantic_tools():
    """L'agent su un modello con embedding include sia CRUD che semantic tools."""
    @resource(operations=["crud"])
    class User(Model):
        id: str = Field(primary_key=True)
        bio: str = Field(embedding=True)

    mock = MockProvider([AgentResponse(content="Done")])

    @agent(model=User, provider=mock)
    class UserAgent:
        pass

    # L'agent runner deve avere il tool semantic_search_users
    tool_names = list(UserAgent._runner.tools.keys())
    assert "semantic_search_users" in tool_names
    assert "create_user" in tool_names
```

---

## 12. Ordine di Implementazione

1. **`core/fields.py`** — aggiungere `embedding=True` a `Field()`, helpers `get_embedding_fields()`, `has_embeddings()`
2. **`embeddings/base.py`** — `BaseEmbeddingProvider` ABC
3. **`embeddings/openai.py`** — `OpenAIEmbeddingProvider`
4. **`embeddings/bedrock.py`** — `BedrockEmbeddingProvider`
5. **`embeddings/__init__.py`** — `get_embedding_provider()`, lazy exports
6. **`vector/base.py`** — `BaseVectorBackend` ABC
7. **`vector/sqlite.py`** — `SQLiteVectorBackend` (brute-force cosine)
8. **`vector/pgvector.py`** — `PgVectorBackend`
9. **`vector/__init__.py`** — `configure_vector_backend()`, auto-detection
10. **`embeddings/pipeline.py`** — `build_embedding_text()`, `generate_and_store_embedding()`, `delete_embedding()`
11. **`resource/crud.py`** — hooks embedding in create/update/delete handlers
12. **`agent/tools.py`** — `build_semantic_tools()`, `_make_semantic_caller()`
13. **`resource/decorator.py`** — endpoint `POST /{resource}/search`
14. **`agent/decorator.py`** — `_resolve_tools()` include semantic tools
15. **`agent/prompt.py`** — system prompt menziona semantic search
16. **`conf/settings.py`** — nuovi default EMBEDDING_*, VECTOR_BACKEND
17. **`cli/builder.py`** — entry point + routes.json aggiornati
18. **Test suite** — pipeline, SQLite backend, tools, agent integration

---

## 13. Dipendenze V3

| Package    | Motivo                           | Scope     |
|------------|----------------------------------|-----------|
| `numpy`    | Cosine similarity (SQLite dev)   | **core**  |
| `openai`   | OpenAIEmbeddingProvider          | optional  |
| `boto3`    | BedrockEmbeddingProvider         | optional  |
| `pgvector` | PgVectorBackend (PostgreSQL)     | optional  |

Nota: `numpy` è l'**unica nuova dipendenza core**. È necessaria per il backend
SQLite (brute-force cosine similarity) e opzionalmente utile anche con pgvector
per preprocessing dei vettori.

---

## 14. Non-Goals (V3)

- Streaming LLM response — il loop agent rimane sincrono
- Conversation history persistente — stateless, `thread_id` è passthrough
- Step Functions / orchestrazione async — il modello sync è sufficiente
- FAISS o vector DB separati (Pinecone, Weaviate) — pgvector basta per prod
- Embedding multimodali (immagini, audio) — solo testo
- Reindexing automatico — se cambi lo schema, devi rigenerare embeddings manualmente
- Auth/permissions su endpoint search
