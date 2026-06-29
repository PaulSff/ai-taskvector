readme = r"""# RunWorkflow

RunWorkflow is the canonical unit that runs a workflow graph when the agent emits the `run_workflow` action.

**Unit type:** `RunWorkflow`

## Purpose

Allows the agent (via ProcessAgent, PayloadTransform, etc.) to execute either:

1. A workflow loaded from a file when `run_workflow.path` is set, or
2. The **current graph** from the `graph` input when `run_workflow.path` is not set.

If neither `run_workflow.path` nor `graph` is available, this unit may fall back to `params["workflow_path"]` (string).

After building Inject defaults, `run_workflow.initial_inputs` (if provided) is merged into the nested executor `initial_inputs` (per-unit shallow merge of port dicts). This supports nested graphs that expect Inject wiring (e.g., `agents/tools/rag_search/rag_context_workflow.json`, `rag/workflows/doc_to_text.json`).

Optional: if `params["zmq"]` is provided, the unit publishes the job to a workflow server and blocks until token/result/error messages are received.

## Interface

### Inputs

| Port / Param | Direction | Type | Description |
|---|---:|---|---|
| `parser_output` (input port) | Input | Any | Must be a dict containing key `run_workflow` (dict). |
| `graph` (input port) | Input | Any | Current graph (dict or `ProcessGraph`) used when no `run_workflow.path` is set. |
| `user_message` (param) | Param | str | Optional message used to populate Inject units (default: `""`; treated as “no message”). |
| `zmq` (param) | Param | dict (optional) | Enables ZMQ job publishing + blocking for results. See **ZMQ** section below. |
| `execution_timeout_s` (param) | Param | float/int (optional) | Timeout for job completion (default: `120.0`). |
| `_stream_callback` (param) | Param | callable (optional) | Streaming callback used for inline status/token updates. |
| `workflow_path` (param) | Param | str (optional) | Fallback workflow path if payload has no `run_workflow.path`. |

### Outputs

| Port | Direction | Type | Description |
|---|---:|---|---|
| `data` (output port) | Output | Any | Execution outputs `{ unit_id: { port_name: value, ... }, ... }` when run was performed; otherwise `{}`. |
| `error` (output port) | Output | str | Error message if load/run failed; empty string on success. |

## Behavior

- If `parser_output` is not a dict or has no `run_workflow` key, no run is performed.
  - Outputs: `data: {}`, `error: ""`
- If `run_workflow` is present but is not a dict, no run is performed.
  - Outputs: `data: {}`, `error: ""`
- Determine workflow source:
  - If `run_workflow.path` is a non-empty string: load workflow graph from that file.
  - Else if `params["workflow_path"]` is a non-empty string: load workflow graph from that path.
  - Else if `graph` input is present: use `graph` as the workflow graph.
  - Else: error.
- Apply `unit_param_overrides`:
  - `run_workflow.unit_param_overrides` (if dict) is applied per-unit by updating each unit’s `params` map.
- Build Inject defaults:
  - The unit scans graph units for `Inject` units.
  - If an Inject unit id is `inject_graph`, it receives `{ "data": <current graph as dict> }`.
  - If `user_message` is non-empty, other Inject units receive `{ "data": <user_message> }`.
- Merge payload `initial_inputs`:
  - If `run_workflow.initial_inputs` is present and is a dict, it is merged into the executor `initial_inputs` after Inject defaults.
  - Merge rule: per-unit shallow merge of port dicts (later values override earlier ones for the same port keys).
- Streaming:
  - If `params["_stream_callback"]` is callable, the unit sends inline status updates using `inline_status_stream_chunk("Thinking…")`.
  - During execution, tokens are forwarded via the same callback.
- Error handling:
  - On exception: `data: {}`, `error: "run_workflow execute failed: <message>"`.
  - Success returns `error: ""`.

## Usage in agent workflow

- `parser` (ProcessAgent) → `run_workflow` (parser_output)
- `inject_graph` → `run_workflow` (graph)
- `run_workflow` (data) → `merge_response` so the GUI receives the run output as `run_output`.

The agent can output either:

- Run the current graph:
  - `{ "action": "run_workflow" }`
- Run a workflow from file:
  - `{ "action": "run_workflow", "path": "/path/to/workflow.json" }`
- Also supported payload fields (inside `run_workflow`):
  - `initial_inputs`, `unit_param_overrides`, `format`

## Input payload shape (from `parser_output["run_workflow"]`)

```json
{
  "path": "...", 
  "initial_inputs": {...},
  "unit_param_overrides": {
    "unit_id": { "param": "value" }
  }
}
```
- `path` (optional): workflow JSON file path.
- `initial_inputs` (optional): per-unit port dicts merged into executor initial_inputs.
- `unit_param_overrides` (optional): per-unit params overrides applied to graph units.

## Params contract

 `_needs_executor = true` MUST be set in params when the GraphExecutor injects the async loop/executor.

## Execute on workflow server over ZMQ (optional)

If `params["zmq"]` is present and there is a dict containing:

- `job_pub_endpoint`
- `response_sub_endpoint`

then this unit publishes a job to the workflow server and blocks until results arrive.

Example of the unit params:

```json
"zmq" = {
  "job_pub_endpoint": "tcp://127.0.0.1:5555",
  "response_sub_endpoint": "tcp://127.0.0.1:5556",
}
"execution_timeout_s" = 30
"_stream_callback" = lambda tok: print("TOKEN:", tok)
```
- Token updates are delivered to _stream_callback (if callable).
- The unit listens for result/error messages and returns outputs on success.
