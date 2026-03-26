# Aggregate

Generic collector: N inputs (Any type) → one `data` dict. Registered as unit type **Aggregate**. Use for LLM context (heterogeneous streams → one structure for Prompt/LLMAgent), or any pipeline that needs to merge multiple inputs into a single dict. Separate from **Join**, which is for RL observation (float inputs → observation vector).

## Behavior

- **Aggregation mode:** Inputs `in_0` … `in_N` are collected into one dict. Key names come from param `keys` (or default to `in_0`, `in_1`, …). Missing values are stored as `""`.
- **Pass-through mode:** If input `data` is already a dict, it is passed through as-is (no aggregation). Use when an upstream unit provides a pre-built context dict.
- **Required keys (optional):** If param `required_keys` is set, any of those keys that are missing or empty (None or whitespace-only string) cause the unit to emit an error message on the `error` output port. If `required_keys` is omitted, no keys are required.

## Interface

| Port / Param      | Direction | Type | Description |
|-------------------|-----------|------|-------------|
| **Inputs**        | data      | Any  | Optional. If a dict, passed through as output `data` (pass-through mode). |
| **Inputs**        | in_0..in_N | Any | Values to merge (aggregation mode). |
| **Outputs**       | data      | Any  | Merged dict (keys from `keys` or in_0, in_1, …) or pass-through dict. |
| **Outputs**       | error     | str  | Non-empty when any `required_keys` entry is missing or empty. |
| **Params**        | num_inputs | int | Limits the number of inputs to aggregate (default 32, max 32). |
| **Params**        | keys      | list | Key names for output dict, e.g. `["user_message", "rag", "graph_summary"]`. If missing or too short, defaults to `in_0`, `in_1`, … |
| **Params**        | required_keys | list | Optional. Keys that must be non-empty; if any are missing/empty, `error` is set. Omit for no validation. |

## Example

**Params:** `{"num_inputs": 3, "keys": ["user_message", "rag", "graph_summary"], "required_keys": ["user_message"]}`

**Inputs:** `{"in_0": "Add a valve", "in_1": "Relevant doc...", "in_2": {"units": [...]}}`  
**Output:** `{"data": {"user_message": "Add a valve", "rag": "Relevant doc...", "graph_summary": {...}}, "error": ""}`

**Entry point:** The runner can supply context via `initial_inputs[aggregate_unit_id] = {"in_0": ..., "in_1": ..., ...}` so the unit has no upstream connections and outputs the combined `data`.
