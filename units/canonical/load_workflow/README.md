# LoadWorkflow

Load a process graph from a file path. Wraps `core.normalizer.load_process_graph_from_file`.

- **Input:** `path` (str) — path to workflow JSON or YAML.
- **Output:** `graph` (dict), `error` (str, optional).
- **Params:** `format` (optional) — infer from suffix if omitted.

Used by the GUI so loading is done via workflow instead of direct Core dependency.
