# `calendar` tool

Manage Calendars ICS files (get_availability, reserve, cancel, create new calendars) via structured JSON actions.

## Parser action

See `prompt.py` for `create_calendar`, `check_availability`, `reserve`, `cancel`, etc.

## `tool.yaml`

- **`workflow`**: `calendar_workflow.json` — inject -> calendar unit for `get_tool_workflow_path("calendar")`.

## Follow-up

`run_todo_manager_follow_up` in `__init__.py` → `TOOL_RUNNERS["calendar"]` in `registry.py`.
