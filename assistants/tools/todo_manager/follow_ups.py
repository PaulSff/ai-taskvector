"""Strings for post-apply rounds when the graph TODO list (or comment + list) changes.

Used by the Flet Workflow Designer chat after canvas apply; any role using the same
``ProcessGraph`` todo_list edit actions can reuse these messages."""

TODO_MANAGER_REVIEW_SYSTEM = (
    "IMPORTANT: The TODO list has been updated. You must review the TODO list. Respond in {session_language}."
)
TODO_MANAGER_REVIEW_USER_MESSAGE = (
    "Review the TODO list and continue. When the job is finished provide a brief summary. Respond in {session_language}."
)
TODO_MANAGER_COMMENT_AND_LIST_SYSTEM = (
    "IMPORTANT: Your comment and the TODO list have been updated. "
    "You must review the comment and TODO list. Respond in {session_language}."
)
TODO_MANAGER_COMMENT_AND_LIST_USER_MESSAGE = (
    "Review your comment and the TODO list. Respond in {session_language}."
)
