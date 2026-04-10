"""grep tool: follow-up prompt fragments."""

from assistants.tools.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

GREP_FOLLOW_UP_PREFIX = "IMPORTANT: You requested a grep search. You must check the result.\n\n"
GREP_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
