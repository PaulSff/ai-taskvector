# Remove Task

Remove a task from the graph’s todo list by task_id. Env-agnostic; used in edit workflows.

## Purpose

Applies a remove_task edit: removes the task with the given id from todo_list.tasks. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the task removed |
| **Params**   | config    | —    | `task_id` — id of the task to remove |

## Example

**Params:** `{"task_id": "task_abc123"}`  
**Input:** `{"graph": {..., "todo_list": {"tasks": [{"id": "task_abc123", ...}]}}}`  
**Output:** `{"graph": {..., "todo_list": {"tasks": []}}}`
