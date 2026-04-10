"""browse skill: follow-up prompt fragments."""

from assistants.skills.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

BROWSE_FOLLOW_UP_PREFIX = "IMPORTANT: You requested the web page content from a URL. You must check the page content.\n\n"
BROWSE_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
