# ExportWorkflow

Export a process graph to an external runtime format. Wraps `core.normalizer.export.from_process_graph`.

- **Input:** `graph` (dict or ProcessGraph).
- **Output:** `exported` (dict/list), `error` (str, optional).
- **Params:** `format` — "node_red" | "pyflow" | "n8n" | "comfyui".

Used by the GUI so export is done via workflow instead of direct Core dependency.
