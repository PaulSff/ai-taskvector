# Import_workflow

Canonical unit that loads a workflow from a file path or URL and converts it to our canonical graph using the import resolver.

- **Input:** `graph` — either a string (path or URL) or a dict with `source` (required) and optional `origin` (e.g. `"node_red"`, `"n8n"`, `"dict"`).
- **Output 0 (`graph`):** Canonical graph dict on success, `None` on failure.
- **Output 1 (`error`):** Error message; empty string on success.

Uses `core.graph.import_resolver.load_workflow_to_canonical`, which loads the source and runs it through the normalizer (`to_process_graph`).
