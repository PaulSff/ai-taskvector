# Add Unit

Add one unit to the graph. Env-agnostic; used in edit workflows. Validation and apply logic live in `assistants/graph_edits.apply_graph_edit`.

## Purpose

Consumes the current graph from the upstream port and applies an add_unit edit: appends one unit (id, type, params). Used by the assistant backend when running an add_unit edit flow.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the new unit added |
| **Params**   | config    | —    | `unit` — object with `id`, `type`, `params` |

## Example

**Params:** `{"unit": {"id": "src1", "type": "Source", "params": {}}}`  
**Input:** `{"graph": {"units": [], "connections": []}}`  
**Output:** `{"graph": {"units": [{"id": "src1", "type": "Source", ...}], "connections": []}}`
