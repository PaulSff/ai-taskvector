# Graph Inject

Outputs the graph provided by the executor as `initial_inputs`. Used at the start of edit workflows (Inject → add_unit → …). Env-agnostic.

## Purpose

In edit flows, the current graph is not produced by an upstream node; the backend injects it when running the flow. This unit has no input ports from connections. The executor must pass `initial_inputs[inject_unit_id] = {"graph": current_graph}` so the unit can forward it to the next node.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | —         | —    | None (graph comes from initial_inputs) |
| **Outputs**  | graph     | any  | The graph dict from initial_inputs |

## Example

**Initial inputs (from backend):** `{"inject": {"graph": {"units": [...], "connections": [...]}}}`  
**Output:** `{"graph": {"units": [...], "connections": [...]}}`
