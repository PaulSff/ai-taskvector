"""report tool: follow-up prompt fragments."""

from assistants.tools.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

REPORT_FOLLOW_UP_PREFIX = (
    "IMPORTANT: Report result from your previous turn.\n\n"
)
REPORT_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
REPORT_FOLLOW_UP_USER_MESSAGE = (
    "Check if the report is created. Summarize the outcome "
    "Respond in {session_language}."
)
