# `todo_manager` tool

Manage TODO lists on the graph (add/remove lists, tasks, mark completed) via structured JSON actions.

## Parser action

See `prompt.py` for `add_todo_list`, `add_task`, `mark_completed`, etc.

## `tool.yaml`

- **`workflow`**: `todo_list.json` — inject + todo list unit for `get_tool_workflow_path("todo_manager")`.

## Follow-up

`run_todo_manager_follow_up` in `__init__.py` → `TOOL_RUNNERS["todo_manager"]` in `registry.py`. Chat integrates with `gui/chat/context/todo_list_manager.py`.
