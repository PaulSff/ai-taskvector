"""read_file tool: follow-up prompt fragments."""

REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a file content. You must check the result and continue.\n\n"
)

REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX = (
    "\n\nInspect the result and address the user's request. "
    "Respond in {session_language}."
)

REQUEST_FILE_CONTENT_FOLLOW_UP_USER_MESSAGE = (
    "Let's check out the file content and continue. Respond in Respond in {session_language}."
)
