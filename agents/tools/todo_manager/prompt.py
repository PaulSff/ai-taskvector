"""Workflow Designer (and any graph editor): JSON edit actions for the canvas TODO list."""

TOOL_ACTION_PROMPT_LINE = """- TODO list actions:
  - add_todo_list: { "action": "add_todo_list", "id": "my_new_todo_list_id", "title": "My new todo list" }
  - remove_todo_list: { "action": "remove_todo_list", "id": "<todo_list_id_to_remove>" }
  - add_task: { "action": "add_task", "text": "Task description..." } (in case of having multiple todo lists specify the list id:  { "action": "add_task", "text": "task description...", "id": "<todo_list_id_to_add_the_task_into>" })
  - remove_task: { "action": "remove_task", "task_id": "..." }
  - mark_completed: { "action": "mark_completed", "task_id": "...", "completed": true }"""
