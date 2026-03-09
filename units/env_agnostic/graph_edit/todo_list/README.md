# todo_list

Single graph-edit unit for all todo-list actions. Replaces the separate add_todo_list, add_task, remove_task, remove_todo_list, and mark_completed units.

## Purpose

Applies one todo-list edit to the current graph (from inject). **Logic lives in the unit**: the unit uses `core.todo_list` (ensure_todo_list, add_task, remove_task, mark_completed) and writes the updated `todo_list` into the graph. **Apply logic lives in core**: when `apply_graph_edit` receives add_todo_list / add_task / remove_task / mark_completed, it uses the same `core.todo_list` functions to apply the edit.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | Any  | Current graph dict (from inject) |
| **Outputs**  | graph     | Any  | Updated graph dict after edit |
| **Params**   | action    | str  | One of: `add_todo_list`, `add_task`, `remove_task`, `remove_todo_list`, `mark_completed` |
| **Params**   | title     | str  | For add_todo_list: optional list title |
| **Params**   | text      | str  | For add_task: task text |
| **Params**   | task_id   | str  | For remove_task, mark_completed: task id |
| **Params**   | completed | bool | For mark_completed: set completed (default true) |

## Edit workflows

Each todo action has its own workflow JSON (e.g. `add_task.json`) that wires inject → todo_list with `params.action` set. The runner merges the edit payload (text, task_id, etc.) into the unit params at runtime.
