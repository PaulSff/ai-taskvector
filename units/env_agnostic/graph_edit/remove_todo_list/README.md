# Remove Todo List

Remove the graph’s todo list. Env-agnostic; used in edit workflows.

## Purpose

Applies a remove_todo_list edit: clears the todo list metadata from the graph. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with todo_list removed |
| **Params**   | config    | —    | None |

## Example

**Input:** `{"graph": {..., "todo_list": {"id": "...", "tasks": [...]}}}`  
**Output:** `{"graph": {...}}` (todo_list key removed or cleared)
