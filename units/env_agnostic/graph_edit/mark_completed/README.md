# Mark Completed

Mark a task in the todo list as completed or incomplete. Env-agnostic; used in edit workflows.

## Purpose

Applies a mark_completed edit: sets the task’s `completed` flag by task_id. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the task’s completed flag updated |
| **Params**   | config    | —    | `task_id` — id of the task; optional `completed` (default true) |

## Example

**Params:** `{"task_id": "task_abc123", "completed": true}`  
**Input:** `{"graph": {..., "todo_list": {"tasks": [{"id": "task_abc123", "completed": false, ...}]}}}`  
**Output:** `{"graph": {..., "todo_list": {"tasks": [{"id": "task_abc123", "completed": true, ...}]}}}`
