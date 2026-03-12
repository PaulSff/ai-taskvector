# Aggregate

Collector: N inputs (Any type) → one `data` dict. Used for LLM context and LLMSet (heterogeneous streams → one structure for Prompt/LLMAgent). Registered as unit type **Aggregate** (n8n keeps its own **Merge** type).

## Purpose

Wires multiple context streams (e.g. user_message, RAG, recent_changes, graph_summary) into a single dict. Use for: user_message, RAG, recent_changes, graph_summary → Aggregate → Prompt → LLMAgent → Switch → actions. Separate from **Join**, which is for RL observation (float inputs → observation vector).

**Entry point:** The same Aggregate unit can be used as the pipeline entry: the runner passes context via `initial_inputs[merge_unit_id] = {"in_0": user_message, "in_1": rag, "in_2": recent_changes, ...}`. That unit has no upstream connections and outputs the combined `data`; no separate Inject needed for the assistant flow.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|--------------|
| **Inputs**   | in_0..in_N | Any | Values from sources (any type) |
| **Outputs**  | data      | Any  | Dict of inputs (keys from param `keys` or in_0, in_1, …) |
| **Params**   | num_inputs | int | Number of inputs (default 8, max 8) |
| **Params**   | keys      | list | Key names for output dict, e.g. `["user_message", "rag", "graph_summary", ...]` |

## Example

**Params:** `{"num_inputs": 3, "keys": ["user_message", "rag", "graph_summary"]}`

**Inputs:** `{"in_0": "Add a valve", "in_1": "Relevant doc...", "in_2": {"units": [...], "connections": [...]}}`  
**Output:** `{"data": {"user_message": "Add a valve", "rag": "Relevant doc...", "graph_summary": {...}}}`
