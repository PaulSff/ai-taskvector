# RunWorkflow

Canonical unit that runs a workflow graph when the assistant emits the `run_workflow` action.

**Unit type:** `RunWorkflow`

## Purpose

Allows the assistant (via ProcessAgent, PayloadTransform, etc.) to run either the **current graph** (from the `graph` input) or a workflow loaded from a file when `run_workflow.path` is set. After building Inject defaults, optional `run_workflow.initial_inputs` is merged in (same shape as `run_workflow()`’s `initial_inputs` argument) so nested graphs like `assistants/tools/rag_search/rag_context_workflow.json` or `doc_to_text.json` receive `rag_search` / `inject_path` wiring without changing those JSON files.

## Interface

| Port / Param   | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input**      | parser_output | Any | Must contain key `run_workflow` (dict). Optional `path`, optional `initial_inputs` (unit_id → port dict merged into the nested run). |
| **Input**      | graph     | Any | Current graph (dict or ProcessGraph). Used when `run_workflow.path` is not set. |
| **Param**      | user_message | str | Optional message for Inject units (default `""` → `"(no message)"`). |
| **Output**     | data      | Any | Execution outputs `{ unit_id: { port_name: value, ... }, ... }` when a run was performed; otherwise `{}`. |
| **Output**     | error     | str | Error message if load/run failed; `None` on success. |

## Behaviour

- If `parser_output` is not a dict or has no `run_workflow` key: no run; outputs `data: {}`, `error: None`.
- If `run_workflow.path` is a non-empty string: load the graph from that file (dict format), then run it.
- If `run_workflow.path` is missing or empty: use the `graph` input as the graph to run. If `graph` is missing, output an error.
- If `run_workflow.initial_inputs` is present, merge it into the nested executor `initial_inputs` after Inject defaults (per-unit shallow merge of port dicts).
- On success, `data` holds the executor outputs; `error` is `None`. On failure, `data` is `{}` and `error` is set.

## Usage in assistant workflow

- **parser** (ProcessAgent) → **run_workflow** (parser_output).
- **inject_graph** → **run_workflow** (graph).
- **run_workflow** (data) → **merge_response** so the GUI receives `run_output` in the response.

The assistant can output `{ "action": "run_workflow" }` to run the current graph, or `{ "action": "run_workflow", "path": "/path/to/workflow.json" }` to run a workflow from file.
