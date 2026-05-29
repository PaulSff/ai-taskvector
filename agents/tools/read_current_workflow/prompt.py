"""Analyst (and any role with a slim graph inject): JSON action line for full graph summary on demand."""

TOOL_ACTION_PROMPT_LINE = (
    '- read_current_workflow: Request the full current process graph summary (units, connections, '
    'code blocks per policy, metadata, todos, comments): { "action": "read_current_workflow" }'
)
