# todo_list

Single graph-edit unit for all todo-list actions. Replaces the separate add_todo_list, add_task, remove_task, remove_todo_list, and mark_completed units.

## Purpose

Applies one or more todo-list edits to the current graph. **Logic lives in the unit**: the unit utilizes `core.graph.todo_list` utilities (such as `normalize_todo_lists`, `create_new_todo_list`, `add_task`, etc.) to update the `todo_lists` key in the graph. It supports both single edits via parameters and batch edits via `Multiple_edits_sequential`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | Any  | Current graph dict (from inject) |
| **Inputs**   | data      | Any  | Additional data input (unused in current logic) |
| **Outputs**  | graph     | Any  | Updated graph dict after edit |
| **Params**   | action    | str  | One of: `add_todo_list`, `remove_todo_list`, `add_task`, `remove_task`, `mark_completed`, `set_implementer`, `set_deadline`, `set_curator` |
| **Params**   | title       | str  | For `add_todo_list`: optional list title |
| **Params**   | id          | str  | For `add_todo_list`/`remove_todo_list`: the ID of the list |
| **Params**   | text        | str  | For `add_task`: task text |
| **Params**   | task_id     | str  | For all task-level actions: the ID of the task |
| **Params**   | todo_list_id| str  | Optional: ID of the list to target. If omitted and only one list exists, that list is used |
| **Params**   | completed   | bool | For `mark_completed`: set completion status |
| **Params**   | implementer  | str  | For `set_implementer`: name/ID of the person assigned |
| **Params**   | deadline     | str  | For `set_deadline`: date/time string |
| **Params**   | curator      | str  | For `set_curator`: name/ID of the curator |

## Edit workflows

### Single Edit
Each todo action can be triggered via a workflow JSON (e.g. `add_task.json`) that wires inject → todo_list with `params.action` set. The runner merges the edit payload into the unit params at runtime.

### Batch Edits
To apply multiple changes in one step, use the `Multiple_edits_sequential` parameter. Pass a list of edit objects: 
`Multiple_edits_sequential=[{"action": "add_task", ...}, {"action": "mark_completed", ...}]`.
