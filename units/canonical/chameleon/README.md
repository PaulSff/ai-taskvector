# Chameleon

Runs a **list of action dicts** in one `step_fn` call, each through a registered unit’s `step_fn(params, inputs, state, dt)`.

## Input

| Port | Type | Description |
|------|------|-------------|
| **actions** | Any | List of dicts, or dict `{"actions": [...] }`. |
| **data** | Any | Same accepted shapes as **actions** if that port is unwired. |

Each item:

| Key | Required | Description |
|-----|----------|-------------|
| **type** | yes | `UnitSpec.type_name` (e.g. `RunWorkflow`, `Debug`). |
| **params** | no | Merged into that unit’s `params` for the call (default `{}`). |
| **inputs** | no | `step_fn` `inputs` dict: port name → value (default `{}`). |

## Output

| Port | Type | Description |
|------|------|-------------|
| **data** | Any | List of `{ "type", "outputs", "error" }` per item. |
| **last** | Any | Output dict from the **last** successful step (empty if none). |
| **error** | str | `None` if every step succeeded; else short joined messages from failed steps. |

## Params

| Name | Default | Description |
|------|---------|-------------|
| **loop_dt** | parent `dt` or `0.1` | `dt` passed to each child `step_fn`. |
| **stream_outputs** | `false` | When `true` and **`_stream_callback`** is set (graph executor passes it when the run uses `stream_callback`), after **each** action finishes Chameleon calls the callback with a JSON payload prefixed by `CHAMELEON_STREAM_PREFIX` in `runtime.stream_ui_signals` (same channel as LLM tokens / inline status). Each chunk includes cumulative **`data`**, **`last`**, running **`error`** summary, **`index`** / **`total`**, the **`step`** just completed, and **`done`** when that step was the last. Final unit return values are unchanged (full list on **`data`**). |
| **_stream_callback** | — | Set by the graph executor when `run_workflow(..., stream_callback=…)` is used. Copied into each child’s `params` when callable; types that do not stream ignore it. With **`stream_outputs`**, Chameleon also emits structured partial chunks (see above). |

## Limits

- **Nested Chameleon** is rejected.
- **code_block_driven** types are skipped (need graph code blocks).
- Child **state** is fresh `{}` per item (no cross-item state carry).

## Example

Wire **actions** or **data** from upstream with a list of `{ "type": "RunWorkflow", "params": {}, "inputs": { "parser_output": { ... }, "graph": null } }` entries (same `inputs` shape as a static **RunWorkflow** node would receive).
