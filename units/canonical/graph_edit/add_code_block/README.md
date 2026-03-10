# Add Code Block

Add a code block (id, source, language) to the graph. Env-agnostic; used in edit workflows.

## Purpose

Applies an add_code_block edit: attaches a code block to a unit for execution (e.g. function node, script). Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the code block added |
| **Params**   | config    | —    | `code_block` — object with `id`, `source`, optional `language` |

## Example

**Params:** `{"code_block": {"id": "fn_1", "source": "return inputs.get('x', 0) + 1", "language": "python"}}`  
**Input:** `{"graph": {"units": [...], "connections": [], "code_blocks": []}}`  
**Output:** `{"graph": {..., "code_blocks": [{"id": "fn_1", "source": "...", "language": "python"}]}}`
