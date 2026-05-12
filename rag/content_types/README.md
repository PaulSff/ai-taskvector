# RAG Content-Type Registry

Semantic content-type registry and routing system for modular RAG architectures.

The registry dynamically discovers content-type packages, classifies uploaded content semantically, routes ingestion workflows, and provides storage/indexing metadata across heterogeneous document families.

Supports:

- Markdown
- Plain text
- JSON
- YAML
- XML
- Future custom content families

---

# Overview

This registry powers the content-classification layer of the RAG pipeline.

It provides:

- Dynamic package discovery
- Semantic runtime classification
- Workflow routing
- Upload normalization
- Storage organization
- Index strategy lookup
- Extension/plugin architecture

The system is intentionally serialization-agnostic.

It does **not** hardcode logic around:
- JSON semantics
- Markdown semantics
- YAML semantics
- XML semantics

Instead, content behavior is delegated to independently installable content-type packages.

---

# Architecture

```text
rag/
└── content_types/
    ├── markdown/
    │   ├── generic_markdown/
    │   │   ├── content_type.yaml
    │   │   ├── discriminant.py
    │   │   └── markdown_extract.json
    │   │
    │   └── obsidian_note/
    │
    ├── json/
    │   ├── openapi_schema/
    │   ├── notebook_export/
    │   └── generic_json/
    │
    ├── yaml/
    └── xml/
```

---

# Core Concepts

## Content Family

A broad serialization or document category.

Examples:

| Family | Examples |
|---|---|
| `markdown` | docs, notes, wiki pages |
| `json` | schemas, exports, configs |
| `yaml` | manifests, pipelines |
| `xml` | feeds, structured docs |

---

## Content Type

A semantic subtype inside a family.

Examples:

| Family | Content Type |
|---|---|
| markdown | `obsidian_note` |
| markdown | `documentation_page` |
| json | `openapi_schema` |
| json | `chat_export` |

Each content type is a self-contained package.

---

## Discriminant

A runtime semantic classifier.

Discriminants determine whether a file belongs to a specific content type.

Each package may provide:

```python
CONTENT_KIND = "openapi"

def matches(path, data):
    ...
```

The registry evaluates discriminants in priority order.

---

# Package Structure

Every content-type package must contain:

```text
content_type.yaml
```

Optional:

```text
discriminant.py
```

Optional workflow assets:

```text
extract_workflow.yaml
```

---

# Example Package

```text
rag/content_types/json/openapi_schema/
├── content_type.yaml
├── discriminant.py
└── extract_openapi.json
```

---

# content_type.yaml

Example:

```yaml
id: openapi_schema

title: OpenAPI Schema

detect:
  suffixes:
    - .json
    - .yaml

  content_kind: openapi

index_strategy: structured-json

constants:
  chunk_size: 1200

workflows:
  extraction: extract_openapi.yaml

mydata_organize:
  subdir: "_organized/apis"
```

---

# Runtime Classification

## classify_content()

Primary semantic classification entrypoint.

```python
result = classify_content(
    path=Path("openapi.json"),
    data=parsed_json,
)
```

Returns:

```python
{
    "family": "json",
    "content_kind": "openapi",
    "id": "openapi_schema",
}
```

---

# Discovery System

The registry dynamically scans:

```text
rag/content_types/<family>/<content-type-id>/
```

Discovery is filesystem-driven.

No central registration file is required.

---

# Registry Lifecycle

## Package Discovery

```python
list_packages()
```

Returns all installed content-type packages.

---

## Package Lookup

```python
get_package("openapi_schema")
```

---

## Registry Refresh

Clears cached registry state.

```python
refresh_registry()
```

Clears:

- package cache
- discriminant cache
- strategy suffix cache

---

# Upload Routing

## upload_router_payload()

Normalizes upload metadata into a routing payload.

Example:

```python
payload = upload_router_payload(
    file_path="spec.json",
    parsed_data=data,
)
```

Produces:

```python
{
    "file_path": "spec.json",
    "suffix": ".json",
    "parsed": {...},
    "family": "json",
    "content_kind": "openapi",
    "content_type_id": "openapi_schema",
}
```

---

# Workflow Routing

Packages may define extraction workflows.

Example:

```yaml
workflows:
  extraction: extract_openapi.json
```

Runtime access:

```python
pkg.extraction_workflow_path()
```

---

# Storage Routing

The registry also controls organized storage destinations.

Example:

```python
mydata_destination(
    mydata=Path("/data"),
    content_kind="openapi",
)
```

Possible output:

```text
/data/_organized/apis
```

---

# Index Strategies

Packages may declare indexing strategies.

Example:

```yaml
index_strategy: structured-json
```

Query supported suffixes:

```python
suffixes_for_strategy("structured-json")
```

---

# Semantic vs Syntactic Classification

The registry distinguishes between:

| Type | Meaning |
|---|---|
| Syntactic | `.json`, `.md`, `.yaml` |
| Semantic | `openapi`, `obsidian_note`, `chat_export` |

This enables:
- specialized chunking
- tailored extraction
- family-specific embedding strategies
- semantic retrieval pipelines

---

# Design Goals

## Generic by Default

The registry avoids embedding assumptions about:
- parsers
- embeddings
- vector stores
- chunking
- retrieval engines

It only provides semantic routing and package metadata.

---

## Extensible

New content types require:
1. a package directory
2. `content_type.yaml`
3. optional discriminant/workflows

No core registry changes are required.

---

## Deterministic

Discriminants are:
- ordered
- prioritized
- cacheable

Classification behavior remains stable and inspectable.

---

# Example: Adding a New Content Type

## 1. Create Package

```text
rag/content_types/json/chat_export/
```

---

## 2. Add content_type.yaml

```yaml
id: chat_export

detect:
  suffixes:
    - .json

content_kind: conversation
```

---

## 3. Add discriminant.py

```python
CONTENT_KIND = "conversation"

PRIORITY = 50

def matches(path, data):
    return (
        isinstance(data, dict)
        and "messages" in data
    )
```

---

# Public API

## Registry

| Function | Purpose |
|---|---|
| `list_packages()` | Discover installed packages |
| `get_package()` | Lookup package |
| `refresh_registry()` | Clear caches |

---

## Classification

| Function | Purpose |
|---|---|
| `classify_content()` | Semantic classification |
| `upload_router_payload()` | Upload normalization |

---

## Routing

| Function | Purpose |
|---|---|
| `mydata_destination()` | Resolve storage destination |
| `suffixes_for_strategy()` | Query indexing support |

---

# Future Extensions

Potential future capabilities:

- MIME-aware classification
- Multi-stage discriminants
- ML-assisted semantic routing
- Registry hot-reload
- Distributed package registries
- Typed config schemas
- Capability negotiation
- Pipeline dependency graphs

---

# Philosophy

The registry treats content types as first-class semantic entities.

Rather than indexing files solely by extension, the system enables:
- semantic ingestion
- semantic workflows
- semantic retrieval behavior

This allows the RAG stack to evolve from:
- generic document ingestion

toward:
- domain-aware knowledge pipelines
- specialized retrieval systems
- content-native processing workflows
