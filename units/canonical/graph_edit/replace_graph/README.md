# Replace Graph

Replace the entire graph with new units and connections. Env-agnostic; used in edit workflows.

## Purpose

Applies a replace_graph edit: replaces `units` and `connections` with the provided lists. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict (may be ignored) |
| **Outputs**  | graph     | any  | New graph from params |
| **Params**   | config    | —    | `units` — list of unit dicts; `connections` — list of connection dicts |

## Example

**Params:** `{"units": [{"id": "a", "type": "Source", "params": {}}], "connections": []}`  
**Output:** `{"graph": {"units": [...], "connections": []}}`
