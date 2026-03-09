# Connect

Add a connection between two units. Env-agnostic; used in edit workflows.

## Purpose

Applies a connect edit: appends a connection from one unit’s output port to another’s input port. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the new connection added |
| **Params**   | config    | —    | `from_id`, `to_id` (or `from`, `to`); optional `from_port`, `to_port` (default `"0"`) |

## Example

**Params:** `{"from_id": "src1", "to_id": "valve_1", "from_port": "0", "to_port": "0"}`  
**Input:** `{"graph": {"units": [...], "connections": []}}`  
**Output:** `{"graph": {"units": [...], "connections": [{"from": "src1", "to": "valve_1", ...}]}}`
