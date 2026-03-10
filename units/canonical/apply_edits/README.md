# ApplyEdits unit

Canonical unit that **applies a list of graph edits** to the current graph and outputs a result plus apply status.

- **Inputs**
  - `graph` (Any) — Current process graph (dict or object with `model_dump`). If missing, treated as empty `{units: [], connections: []}`.
  - `edits` (Any) — List of edit payloads (e.g. from ProcessAgent), or a dict with an `"edits"` key. Only edits whose `action` is a graph-edit action are applied; others are skipped so other units (e.g. RagSearch) can consume them.
- **Outputs**
  - `result` (Any) — Dict with `kind` (`"no_edits"` | `"applied"` | `"apply_failed"`), `content_for_display`, `graph` (updated graph on success), `edits`, and `last_apply_result` (includes `graph_after` as an LLM-friendly summary).
  - `status` (Any) — Apply result: `attempted`, `success`, `error`, and optionally `edits_summary`.
  - `graph` (Any) — Updated graph after applying edits (or unchanged if no edits / apply failed). Used by downstream units e.g. GraphDiff for `current_graph`.

Used in the assistant workflow: **graph** from upstream (e.g. Inject), **edits** from ProcessAgent → **ApplyEdits** → `result` and `status`.

The unit has no parameters; `import_workflow` edits are resolved from file/URL inside `core.graph.batch_edits` (no RAG catalog).

## Implementation

The unit delegates to `core.graph.batch_edits.apply_workflow_edits()` for applying edits (including import resolution and runtime policy checks) and to `core.graph.summary.graph_summary()` for the `graph_after` summary. It has no dependency on `assistants`; it is standalone within `core.graph` and the unit layer.
