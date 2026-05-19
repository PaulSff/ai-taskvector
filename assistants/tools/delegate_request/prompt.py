"""Analyst (and optional roles): JSON action line for delegate_request."""

TOOL_ACTION_PROMPT_LINE = (
    "- delegate_request: Hand the conversation to another chat assistant, output the following JSON block: "
    '{ "action": "delegate_request", "delegate_to": "...", "message": "optional short follow-up for the delegatee." } '
    "use the assistant's role name."
)

# 'Optional: { "action": "delegate_request", "delegate_to": "analyst", "message": "Shorter follow-up for the next agent." }'
