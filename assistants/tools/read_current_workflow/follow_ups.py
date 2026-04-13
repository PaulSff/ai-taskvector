"""read_current_workflow tool: follow-up prompt fragments."""

from assistants.tools.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

READ_CURRENT_WORKFLOW_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the full current workflow graph summary. Use the JSON below.\n\n"
)

READ_CURRENT_WORKFLOW_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
