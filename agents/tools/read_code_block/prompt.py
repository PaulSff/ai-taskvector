"""Workflow Designer: JSON action line for read_code_block."""

TOOL_ACTION_PROMPT_LINE = (
    '- read_code_block: Only if you lack information, request the source of a code block from the graph: '
    '{ "action": "read_code_block", "id": "unit_id" }.'
)
