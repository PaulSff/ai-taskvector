# RunWorkflow

Canonical unit that runs a workflow graph when the assistant emits the `run_workflow` action.

**Unit type:** `RunWorkflow`

## Purpose

Allows the assistant (via ProcessAgent-parsed action `{ "action": "run_workflow", "path": "optional path" }`) to run either the **current graph** (from the `graph` input, e.g. from `inject_graph`) or a workflow loaded from a file when `path` is set. Execution uses the same logic as the workflow tab Run button: build initial inputs for Inject units, run the graph once via `GraphExecutor`, and output the results.

## Interface

| Port / Param   | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input**      | parser_output | Any | Full parser output (from ProcessAgent `edits`). Must contain key `run_workflow` with optional `path` to trigger a run. |
| **Input**      | graph     | Any | Current graph (dict or ProcessGraph). Used when `run_workflow.path` is not set. |
| **Param**      | user_message | str | Optional message for Inject units (default `""` → `"(no message)"`). |
| **Output**     | data      | Any | Execution outputs `{ unit_id: { port_name: value, ... }, ... }` when a run was performed; otherwise `{}`. |
| **Output**     | error     | str | Error message if load/run failed; `None` on success. |

## Behaviour

- If `parser_output` is not a dict or has no `run_workflow` key: no run; outputs `data: {}`, `error: None`.
- If `run_workflow.path` is a non-empty string: load the graph from that file (dict format), then run it.
- If `run_workflow.path` is missing or empty: use the `graph` input as the graph to run. If `graph` is missing, output an error.
- On success, `data` holds the executor outputs; `error` is `None`. On failure, `data` is `{}` and `error` is set.

## Usage in assistant workflow

- **parser** (ProcessAgent) → **run_workflow** (parser_output).
- **inject_graph** → **run_workflow** (graph).
- **run_workflow** (data) → **merge_response** so the GUI receives `run_output` in the response.

The assistant can output `{ "action": "run_workflow" }` to run the current graph, or `{ "action": "run_workflow", "path": "/path/to/workflow.json" }` to run a workflow from file.
