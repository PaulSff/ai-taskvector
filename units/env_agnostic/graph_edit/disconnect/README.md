# Disconnect

Remove a connection between two units. Env-agnostic; used in edit workflows.

## Purpose

Applies a disconnect edit: removes the connection matching the given from/to (and optional ports). Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the connection removed |
| **Params**   | config    | —    | `from_id`, `to_id` (or `from`, `to`); optional `from_port`, `to_port` |

## Example

**Params:** `{"from_id": "src1", "to_id": "valve_1"}`  
**Input:** `{"graph": {"units": [...], "connections": [{"from": "src1", "to": "valve_1", ...}]}}`  
**Output:** `{"graph": {"units": [...], "connections": []}}`
