"""read_file skill: follow-up prompt fragments."""

from assistants.skills.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX = "IMPORTANT: You requested a file content. You must check the content.\n\n"
REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
