# Add Todo List

Add a todo list to the graph (metadata; not exported to runtimes). Env-agnostic; used in edit workflows.

## Purpose

Applies an add_todo_list edit: creates or sets the graph’s todo list with optional title. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with todo list added/updated |
| **Params**   | config    | —    | Optional `title` |

## Example

**Params:** `{"title": "Sprint tasks"}`  
**Input:** `{"graph": {"units": [...], "connections": []}}`  
**Output:** `{"graph": {..., "todo_list": {"id": "todo_list_default", "title": "Sprint tasks", "tasks": []}}}`
