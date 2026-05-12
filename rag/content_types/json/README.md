# JSON Content Types

This folder groups all JSON-based content type packages and their shared extraction workflow.

## Folder Structure

```ai-taskvector/rag/content_types/json/README.md#L1-1
json/
├── json_kind_index_extract.json   ← shared extraction subflow (see below)
├── chat-history/                  ← content_kind: chat_history
├── json-generic/                  ← content_kind: generic  (default / catch-all)
├── n8n-workflow/                  ← content_kind: n8n
├── node-red-catalogue/            ← content_kind: node_red_catalogue
├── node-red-workflow/             ← content_kind: node_red
└── taskvector-workflow/           ← content_kind: canonical
```

Each sub-folder is a self-contained content type package: a `content_type.yaml` that
declares the `json_kind` discriminant and an optional `discriminant.py` that implements
the `matches(path, data) -> bool` function used by the registry to classify JSON files
at ingest time.

---

## Extraction Subflow — `json_kind_index_extract.json`

### Role in the System

`json_kind_index_extract.json` is a **subflow**: it is never run directly. It is
invoked by the parent pipeline `rag/workflows/rag_upload_pipeline.json` via a
`PayloadTransform` → `RunWorkflow` pair whenever a `.json` file is detected.

### Parent Pipeline Trigger

```
rag_upload_pipeline.json
└── PayloadTransform (pt_run)
    └── route: suffix ends_with ".json"
        └── RunWorkflow → rag/content_types/json/json_kind_index_extract.json
```

The parent passes the file path as the initial input:
```json
"initial_inputs": {
  "inject_path": { "data": "{file_path}" }
}
```

### Subflow Architecture

```
inject_path (file path)
    │
    ▼
RagDetectOrigin          — classifies the JSON: chat_history | canonical |
    │                       node_red | n8n | generic
    │ context {file_path, parsed, origin}
    ▼
    PayloadTransform
    ├── route_0  chat_history  → ChatHistoryExtract    → RagChunkBuilder
    ├── route_1  canonical     → CanonicalWorkflowExtract → RagChunkBuilder
    ├── route_2  node_red      → NodeRedWorkflowExtract   → RagChunkBuilder
    ├── route_3  n8n           → N8nWorkflowExtract       → RagChunkBuilder
    └── route_4 generic   → JsonFlattenExtract        → RagChunkBuilder
```

The subflow outputs a list of `chunks` — each chunk being a
`{ "text": "...", "metadata": { ... } }` dict — which are collected by the parent
pipeline's `RagFlattenChunks` unit and passed on to `RagBuildIndexDocument`,
`Embedder`, and `ChromaIndexer`.

### Extraction Strategies

| Route | Extractor | Strategy |
| :--- | :--- | :--- |
| `chat_history` | `ChatHistoryExtract` | One item per message `{role, content}` |
| `canonical` | `CanonicalWorkflowExtract` | One item per unit/node in the workflow |
| `node_red` | `NodeRedWorkflowExtract` | One item per Node-RED node |
| `n8n` | `N8nWorkflowExtract` | One item per n8n node |
| `generic` (default) | `JsonFlattenExtract` | Recursively flattens any JSON into `key: value` text pairs |

### The Generic / Catalogue Path

Any JSON that does not match a specific discriminant (including Node-RED catalogue
files, which `RagDetectOrigin` remaps from `node_red_catalogue` → `generic`) is
handled by `JsonFlattenExtract`. It:

- Recursively walks the JSON structure up to `max_depth` levels (default: 5).
- Joins primitive leaf values as `key: value | nested.key: value | ...` text.
- Promotes well-known top-level fields (`id`, `name`, `description`, `keywords`,
  `categories`, `url`, etc.) into the `metadata` dict for Chroma filtering.
- If the top-level JSON is an **array**, one RAG item is produced per element.

Configurable via unit params: `max_depth`, `max_value_len`, `max_pairs`, `skip_keys`.

---

## Adding a New JSON Type

1. Create a new sub-folder: `json/<my-type>/`.
2. Add `content_type.yaml`:
   ```yaml
   id: my-type
   title: My Type
   detect:
     json_kind: my_kind
   mydata_organize:
     subdir: _organized/MyType
   workflows:
     extraction: ../json_kind_index_extract.json
   constants: {}
   ```
3. Add `discriminant.py` with `JSON_KIND`, `PRIORITY`, and `matches(path, data)`.
4. Add a new route to `Router` in `json_kind_index_extract.json` and a matching
   extractor + `RagChunkBuilder` pair.

The registry discovers the new package automatically on next load (no code changes
required in `registry.py`).
