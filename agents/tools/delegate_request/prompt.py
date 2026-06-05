"""Analyst (and optional roles): JSON action line for delegate_request."""

TOOL_ACTION_PROMPT_LINE = (
    "- delegate_request: Hand over the current request to the best suitable role, output the following JSON block: "
    '{ "action": "delegate_request", "delegate_to": "workflow_designer (the role to delegatee)", "message": "User wants to ..." } '
    ' where the "message" must be in {language}'
)
