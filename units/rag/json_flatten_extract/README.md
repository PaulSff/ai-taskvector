# JsonFlattenExtract

Generic RAG extractor for any JSON file or in-memory JSON object. Recursively walks
the JSON structure and converts it into a searchable `key: value` text string, making
arbitrary JSON findable in the vector index without requiring a hand-crafted schema.

---

## Role in the pipeline

`JsonFlattenExtract` is the **default (catch-all) extractor** in
`rag/content_types/json/json_kind_index_extract.json`. When `RagDetectOrigin`
classifies a JSON file as `generic` (i.e. it is not a known workflow, chat history,
or catalogue format), the Router sends the context envelope to this unit.

```
RagDetectOrigin
    └── origin: "generic"
            ↓
        Router (default port)
            ↓
        JsonFlattenExtract  ← this unit
            ↓
        RagChunkBuilder
```

---

## Input ports

| Port | Type | Description |
| :--- | :--- | :--- |
| `data` | Any | Accepts a bare file-path string, a parsed JSON dict/list, or a `RagDetectOrigin` context envelope `{file_path, parsed, origin}`. |
| `file_path` | Any | Optional override. When provided as a non-empty string, takes precedence over any path found in `data`. |

---

## Output ports

| Port | Type | Description |
| :--- | :--- | :--- |
| `items` | Any | List of `{text, metadata}` dicts ready for `RagChunkBuilder`. One item per top-level dict; one item per element if the JSON root is an array. |
| `error` | str | Non-empty on failure; `items` is `[]` in that case. |

---

## Text format

Each item's `text` field is a `" | "`-separated string of `key: value` pairs built
from every leaf value in the JSON object:

```
id: node-red-contrib-http | description: HTTP nodes for flows | keywords: http rest api | categories: network
```

**Rules:**
- Keys use dot notation for nested structures: `meta.author: Jane`
- Lists of primitives are space-joined into a single value: `keywords: http rest api`
- Dicts nested inside lists are recursed into using the parent key as prefix
- Values longer than `max_value_len` are truncated with `...`
- Up to `max_pairs` key-value pairs are kept per item (longest-first is NOT applied;
  pairs appear in dict iteration order, capped at the limit)

---

## Metadata

The `metadata` dict always contains `file_path` and `origin`. Any of the following
**well-known top-level fields** found in the JSON are also promoted into metadata for
Chroma filtering:

`id` · `name` · `title` · `description` · `version` · `author` · `url` · `source` ·
`category` · `categories` · `type` · `tags` · `keywords` · `origin` · `label`

Dict/list values for these fields are JSON-serialised to strings.

---

## Params

| Param | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `max_depth` | int | `5` | Maximum nesting depth to recurse into. Clamped to `[1, 10]`. |
| `max_value_len` | int | `400` | Maximum characters per value string before truncation. Clamped to `[50, 2000]`. |
| `max_pairs` | int | `80` | Maximum number of `key: value` pairs per item. Clamped to `[1, 500]`. |
| `skip_keys` | list[str] | `[]` | Top-level keys to exclude entirely from flattening. |

All params are optional. The defaults work well for most generic JSON files.

---

## Examples

### Catalogue module (single dict)
```json
{"id": "node-red-contrib-http", "description": "HTTP nodes", "keywords": ["http", "rest"]}
```
→ `text`: `"id: node-red-contrib-http | description: HTTP nodes | keywords: http rest"`  
→ `metadata`: `{"file_path": "...", "origin": "generic", "id": "node-red-contrib-http", "description": "HTTP nodes", "keywords": "[\"http\", \"rest\"]"}`

### Top-level array (e.g. catalogue with multiple modules)
```json
[{"id": "module-a", ...}, {"id": "module-b", ...}]
```
→ **Two items** are produced, one per element.

### Nested config file
```json
{"server": {"host": "localhost", "port": 8080}, "debug": true}
```
→ `text`: `"server.host: localhost | server.port: 8080 | debug: True"`
