# Replace Unit

Replace an existing unit with another (same or different type). Env-agnostic; used in edit workflows.

## Purpose

Applies a replace_unit edit: finds a unit by criteria (`find_unit`) and replaces it with a new unit definition (`replace_with`). Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the unit replaced |
| **Params**   | config    | —    | `find_unit` — criteria to find the unit; `replace_with` — new unit (id, type, params) |

## Example

**Params:** `{"find_unit": {"id": "valve_1"}, "replace_with": {"id": "valve_1", "type": "Valve", "params": {"setpoint": 0.5}}}`  
**Input:** `{"graph": {"units": [{"id": "valve_1", ...}], "connections": [...]}}`  
**Output:** `{"graph": {"units": [{"id": "valve_1", "type": "Valve", "params": {...}}], "connections": [...]}}`
