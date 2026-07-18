"""calendar tool: follow-up prompt fragments."""

from agents.tools.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

CALENDAR_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the Callendar action. You must check the results and share the summary with the user.\n\n"
)
CALENDAR_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
