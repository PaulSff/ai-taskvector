"""Workflow Designer (and any graph editor): JSON edit actions for the canvas TODO list."""

TOOL_ACTION_PROMPT_LINE = """- TODO list actions:
  - add_todo_list: { "action": "add_todo_list", "id": "my_new_todo_list_id", "title": "My new todo list" }
  - remove_todo_list: { "action": "remove_todo_list", "id": "<todo_list_id_to_remove>" }
  - add_task: { "action": "add_task", "todo_list_id": "<todo_list_id_to_attach_new_task>" "text": "Task description..." }
  - remove_task: { "action": "remove_task", "task_id": "...", "todo_list_id": "<todo_list_id_to_remove_task_from>" }
  - mark_completed: { "action": "mark_completed", "task_id": "...", "todo_list_id": "<todo_list_id_where_the_task_lives_in>", "completed": true }"""

 # Additional actions supported, but not published yet:
 # - set_implementer: {"action": "set_implementer", "task_id": "<task_id>", "implementer": "<optional_nonempty_or_null_string>", "todo_list_id": "<todo_list_id>"}
 # - set_deadline: {"action": "set_deadline", "task_id": "<task_id>", "deadline": "<estimation_in_sec_for_the_task_to_complete_from_now>", "todo_list_id": "<_todo_list_id>"}
 # - set_curator: {"action": "set_curator", "task_id": "<task_id>", "curator": "<optional_nonempty_or_null_string>", "todo_list_id": "<todo_list_id>"}
 # - set_todo_list_title: {"action": "set_todo_list_title", "todo_list_id": "...", title: "..."}
