"""Workflow Designer: JSON action line for report."""

TOOL_ACTION_PROMPT_LINE = (
    '- report: Generate a structured summary for the user and save it as a file: '
    '{ "action": "report", "output_format": "md" | "csv", "text": { ... } }. '
    'Formatting: MD: { "title", "summary", "sections": [{ "heading", "body" }] }; '
    'CSV: { "headers": [...], "rows": [[...], ...] }.'
)
