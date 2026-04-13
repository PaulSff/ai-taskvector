"""Analyst (and optional roles): JSON action line for delegate_request."""

TOOL_ACTION_PROMPT_LINE = (
    '- delegate_request: Hand the conversation to another chat assistant (new session, same user message by default): '
    '{ "action": "delegate_request", "delegate_to": "workflow_designer" } '
    'or use the assistant\'s display role name. Optional: '
    '{ "action": "delegate_request", "delegate_to": "analyst", "message": "Shorter follow-up for the next assistant." }'
)
