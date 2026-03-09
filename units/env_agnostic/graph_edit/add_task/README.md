# Add Task

Add a task to the graph’s todo list. Env-agnostic; used in edit workflows.

## Purpose

Applies an add_task edit: appends a task (text) to the todo list. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the task added to todo_list.tasks |
| **Params**   | config    | —    | `text` — task description |

## Example

**Params:** `{"text": "Wire valve to sensor"}`  
**Input:** `{"graph": {..., "todo_list": {"tasks": []}}}`  
**Output:** `{"graph": {..., "todo_list": {"tasks": [{"id": "...", "text": "Wire valve to sensor", "completed": false, ...}]}}}`
