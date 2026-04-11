"""Workflow Designer (and any graph editor): JSON edit actions for the canvas TODO list."""

TOOL_ACTION_PROMPT_LINE = """- TODO list actions:
  - add_todo_list: { "action": "add_todo_list", "title": "My new todo list" }
  - remove_todo_list: { "action": "remove_todo_list" }
  - add_task: { "action": "add_task", "text": "task description..." }
  - remove_task: { "action": "remove_task", "task_id": "..." }
  - mark_completed: { "action": "mark_completed", "task_id": "...", "completed": true } (completed defaults to true)"""
