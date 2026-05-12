# RagDetectOrigin

Canonical unit that detects workflow/graph **origin** using `rag.content_types.registry.classify_content` (package `discriminant.py` under `rag/content_types/<id>/`).

- **Inputs:** `graph` — JSON root, JSON string, ``.json`` file path, or ``{parsed, file_path}`` bundle. `path` — optional file path when `graph` is omitted (upload pipelines). 
- **Output 0 (`origin`):** One of `n8n` | `node_red` | `canonical` | `chat_history` | `generic`
- **Output 1 (`graph`):** Same graph passed through (bypass) for downstream wiring.
- **Output 2 (`error`):** Error message if detection failed, else empty string.
- **Output 3 (`context`):** ``{file_path, parsed, origin}`` for Router + **extractors** downstream.

Use this unit when you need to branch or label by origin (e.g. route to different extractors, set `origin` metadata, or filter by format) without changing the graph.
