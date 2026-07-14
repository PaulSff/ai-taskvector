"""Graph metadata: leave a note on the process graph (commenter is set by the host from the active agent role)."""

TOOL_ACTION_PROMPT_LINE = """ - Leave a useful note on the graph:
    - add_comment:  { "action": "add_comment", "info": "..." }
    - remove_comment: { "action": "remove_comment", "comment_id": "<comment_id_to_remove>" }"""
