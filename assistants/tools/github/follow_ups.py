"""github tool: follow-up prompt fragments."""

from assistants.tools.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

GITHUB_FOLLOW_UP_PREFIX = "IMPORTANT: You requested GitHub data. You must check the result.\n\n"
GITHUB_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
