# Remove Unit

Remove one unit from the graph by id. Env-agnostic; used in edit workflows.

## Purpose

Applies a remove_unit edit: deletes the unit and any connections involving it. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the unit and its connections removed |
| **Params**   | config    | —    | `unit_id` — id of the unit to remove |

## Example

**Params:** `{"unit_id": "valve_1"}`  
**Input:** `{"graph": {"units": [..., {"id": "valve_1", ...}], "connections": [...]}}`  
**Output:** `{"graph": {"units": [...], "connections": [...]}}` (valve_1 and its connections gone)
