# RagDetectOrigin

Canonical unit that detects workflow/graph **origin** using `rag.content_types.registry.classify_content` (package `discriminant.py` under `rag/content_types/<id>/`).

- **Inputs:** `graph` — JSON root, JSON string, `.json`/`.yaml`/`.yml` file path, or `{parsed, file_path}` bundle. `path` — optional file path when `graph` is omitted (upload pipelines).  
- **Output 0 (`origin`):** One of `n8n` | `node_red` | `canonical` | `chat_history` | `json-generic` (or other `content_kind` values returned by your discriminants).  
- **Output 1 (`graph`):** Normalized parsed graph (dict/list) used for classification.  
- **Output 2 (`error`):** Error message if detection failed, else empty string.  
- **Output 3 (`context`):** `{"file_path", "parsed", "origin"}` for Router + extractors downstream.

Use this unit when you need to branch or label by origin (e.g., route to different extractors, set `origin` metadata, or filter by format) without changing the graph.

## Behavior notes

- The unit attempts JSON parsing first for strings and file contents; on JSON decode failure it falls back to YAML using `yaml.safe_load` (requires PyYAML).
- Recognizes `.json`, `.yaml`, and `.yml` file extensions.
- Scalar YAML documents (e.g., `42` or `true`) are wrapped into `{"value": <scalar>}` so they can be classified.
- If PyYAML is not installed and YAML fallback is required, parsing fails and the unit returns `origin: "json-generic"` with `graph: None` (the error will mention PyYAML is missing).
- The `file_path` hint (a Path) is passed to `classify_content` so discriminants may use filename heuristics.

## Examples (inputs → outputs)

1) JSON file path
- Input:
  - graph: `data/workflow.json`  (file contains `{"type":"n8n","nodes":[...]}`)
- Output:
  - origin: `n8n`
  - graph: `{ "type": "n8n", "nodes": [...] }`
  - error: `""`
  - context: `{ "file_path": "data/workflow.json", "parsed": { ... }, "origin": "n8n" }`

2) YAML file path
- Input:
  - graph: `uploads/flow.yaml`  (file contains YAML equivalent of a workflow)
- Output (with PyYAML installed):
  - origin: e.g., `node_red`
  - graph: parsed dict/list (or `{"value": ...}` for scalar)
  - error: `""`
  - context: `{ "file_path": "uploads/flow.yaml", "parsed": ..., "origin": "node_red" }`
- Output (without PyYAML):
  - origin: `json-generic`
  - graph: `None`
  - error: contains `"PyYAML not installed"` when YAML fallback was needed

3) Inline JSON string
- Input:
  - graph: `{"type":"canonical","steps":[...]}`
- Output:
  - origin: `canonical`
  - graph: `{ "type": "canonical", "steps": [...] }`
  - error: `""`
  - context: `{ "file_path": "{\"type\":\"...\"}", "parsed": {...}, "origin": "canonical" }`

4) Inline YAML string
- Input:
  - graph: 
    ```
    type: chat\_history
    messages:
      - sender: user
        text: hi
    ```
- Output (with PyYAML):
  - origin: `chat_history`
  - graph: `{ "type": "chat_history", "messages": [...] }`
  - error: `""`
  - context: `{ "file_path": "type: chat_history\n...", "parsed": {...}, "origin": "chat_history" }`

5) Bundle with parsed value
- Input:
  - graph: `{ "parsed": {"type":"n8n","nodes":[...]}, "file_path": "orig.json" }`
- Output:
  - origin: `n8n`
  - graph: `{ "type":"n8n","nodes":[...] }`
  - error: `""`
  - context: `{ "file_path": "orig.json", "parsed": {...}, "origin": "n8n" }`

## Unit Test

```bash
cd units/rag/rag_detect_origin/
pytest -q test_rag_detect_origin.py
```
