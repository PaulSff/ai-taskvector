# Inject

Forwards any valid JSON/dict structure from the executor’s `initial_inputs` as a single output `data`. Env-agnostic; any unit can use it for data injection.

## Purpose

Data for the flow is not always produced by an upstream node; the backend injects it when running the graph. This unit has no input ports from connections. The executor must pass `initial_inputs[inject_unit_id] = { ... }` with any valid structure (e.g. `{"graph": ...}` for edit flows, `{"graph", "user_message", "history", ...}` for assistant flows, or a **subflow** to inject for merge/run downstream). The unit forwards that payload unchanged as output port `data`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | —         | —    | None (all data comes from initial_inputs) |
| **Outputs**  | data      | Any  | The full payload from initial_inputs (any valid JSON/dict) |

## Examples

**Edit flow (graph only):**  
`initial_inputs["inject"] = {"graph": {"units": [...], "connections": [...]}}`  
→ Output: `{"data": {"graph": {"units": [...], "connections": [...]}}}`

**Assistant flow (full context):**  
`initial_inputs["inject"] = {"graph": ..., "user_message": "...", "history": [...], "units_library": "..."}`  
→ Output: `{"data": { ... same keys and structure ... }}`

**Subflow:**  
`initial_inputs["inject"] = {"subflow": {"units": [...], "connections": [...]}}` or the subflow as the root payload.  
→ Output: `{"data": { ... }}`. Downstream units can merge or run the subflow.

Downstream units connect to `data` and use the structure as needed (e.g. `data["graph"]`, `data["user_message"]`, `data["subflow"]`).
