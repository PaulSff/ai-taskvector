# RagDetectOrigin

Canonical unit that detects workflow/graph **origin** using the same structure heuristics as the RAG discriminant (`rag.discriminant.classify_json_for_rag`).

- **Input:** `graph` — workflow or catalogue data (dict, list, or ProcessGraph).
- **Output 0 (`origin`):** One of `n8n` | `node_red` | `canonical` | `chat_history` | `generic`
- **Output 1 (`graph`):** Same graph passed through (bypass) for downstream wiring.
- **Output 2 (`error`):** Error message if detection failed, else empty string.

Use this unit when you need to branch or label by origin (e.g. route to different extractors, set `origin` metadata, or filter by format) without changing the graph.
