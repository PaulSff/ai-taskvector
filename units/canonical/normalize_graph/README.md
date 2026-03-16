# NormalizeGraph

Normalize a raw graph to ProcessGraph and output as dict. Wraps `core.normalizer.to_process_graph`.

- **Input:** `graph` (dict or ProcessGraph).
- **Output:** `graph` (dict), `error` (str, optional).
- **Params:** `format` (optional) — "dict" | "yaml".

Used by the GUI and runners so normalization is done via workflow instead of direct Core dependency.
