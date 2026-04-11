"""Workflow Designer: JSON action line for grep."""

TOOL_ACTION_PROMPT_LINE = (
    '- grep: Search inside a file content or raw text (e.g. logs): { "action": "grep", "pattern": "...", "source": "path or text" }. '
    'source = file path (e.g. log.txt) or inline text; omit to use upstream input.'
)
