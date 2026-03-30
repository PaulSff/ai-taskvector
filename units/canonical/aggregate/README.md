# Aggregate

Generic collector: N inputs (Any type) → one `data` dict. Registered as unit type **Aggregate**. Use for LLM context (heterogeneous streams → one structure for Prompt/LLMAgent), or any pipeline that needs to merge multiple inputs into a single dict. Separate from **Join**, which is for RL observation (float inputs → observation vector).

## Behavior

- **Aggregation mode:** In order to enable the aggregation mode leave the input `port 0` spare (with NO CONNECTIONS to it). Use the inputs starting from `port 1` (the ones named as `in_0` … `in_N` are collected into one dict). Key names come from param `keys` (or default to `in_0`, `in_1`, …). Missing values are stored as `""`. The `num_inputs` in params must match exaclty the numbers of incoming connections in order for the `keys` to correspond to its ports correclty.
- **Pass-through mode:** Sending a dict on the `Input 0` (`"name": "data"`) will get the pass-through mode activated (no aggregation is made, all the remaining inputs are ignored). The input `data` is getting passed through as-is. Use when an upstream unit provides a **pre-built context dict**.
- **Required keys (optional):** If param `required_keys` is set, any of those keys that are missing or empty (None or whitespace-only string) cause the unit to emit an error message on the `error` output port. If `required_keys` is omitted, no keys are required.

## Interface

| Port / Param      | Direction | Type | Description |
|-------------------|-----------|------|-------------|
| **Inputs**        | data      | Any  | Optional pass though port. If a dict, passes through as output `data` (pass-through mode). |
| **Inputs**        | in_0..in_N | Any | Values to merge (aggregation mode). |
| **Outputs**       | data      | Any  | Merged dict (keys from `keys` or in_0, in_1, …) or pass-through dict. |
| **Outputs**       | error     | str  | Non-empty when any `required_keys` entry is missing or empty. |
| **Params**        | num_inputs | int | Must match exactly the number of incoming connections (default 32, max 32). |
| **Params**        | keys      | list | Key names for output dict, e.g. `["user_message", "rag", "graph_summary"]`. If missing or too short, defaults to `in_0`, `in_1`, … |
| **Params**        | required_keys | list | Optional. Keys that must be non-empty; if any are missing/empty, `error` is set. Omit for no validation. |

## Example

**Params:** `{"num_inputs": 3, "keys": ["user_message", "rag", "graph_summary"], "required_keys": ["user_message"]}`

**Inputs:** `{"in_0": "Add a valve", "in_1": "Relevant doc...", "in_2": {"units": [...]}}`  
**Output:** `{"data": {"user_message": "Add a valve", "rag": "Relevant doc...", "graph_summary": {...}}, "error": ""}`

**Entry point:** The runner can supply context via `initial_inputs[aggregate_unit_id] = {"in_0": ..., "in_1": ..., ...}` so the unit has no upstream connections and outputs the combined `data`.
