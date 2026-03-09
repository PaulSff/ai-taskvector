# No Edit

Pass-through: output the graph unchanged. Env-agnostic; used in edit workflows.

## Purpose

Applies a no_edit action: returns the current graph as-is. Useful when the assistant decides not to change the graph (optional `reason` in params). Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Same graph |
| **Params**   | config    | —    | Optional `reason` |

## Example

**Params:** `{"reason": "No change needed"}`  
**Input:** `{"graph": {"units": [...], "connections": [...]}}`  
**Output:** `{"graph": {"units": [...], "connections": [...]}}`
