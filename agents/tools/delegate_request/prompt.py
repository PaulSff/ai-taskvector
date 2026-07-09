"""Analyst (and optional roles): JSON action line for delegate_request."""

TOOL_ACTION_PROMPT_LINE = (
    "- delegate_request: Hand over the current request to the best suitable role, output the following JSON block: "
    '{ "action": "delegate_request", "delegate_to": "<the role-delegatee>", "message": "User wants to ...<brief follow-up, 6 words at max>" } '
    ' where the "message" must be in {language}'
)
