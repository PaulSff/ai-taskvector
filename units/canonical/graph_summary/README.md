# GraphSummary unit

Canonical unit that **produces an LLM-friendly summary** from a process graph.

- **Input**
  - `graph` (Any) — Current process graph (dict or object with `model_dump`). If missing, returns empty summary.
- **Output**
  - `summary` (Any) — Dict with units, connections, environment_type, metadata, comments, todo_list, etc. (same as `core.graph.summary.graph_summary`).

Used in the assistant workflow so the runner injects only the graph; the workflow produces the summary and feeds it to Merge (graph_summary key) and UnitsLibrary. Replaces the need for a separate `inject_graph_summary` inject.

Implementation delegates to `core.graph.summary.graph_summary()`.
