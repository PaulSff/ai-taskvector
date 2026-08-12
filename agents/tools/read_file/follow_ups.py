"""read_file tool: follow-up prompt fragments."""

REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a file content. You must check the content.\n\n"
)

REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX = (
    "\n\nInspect the content and address the user's request, check the previous turn to understand the context. If the user wanted to generate a file, output the corresponding JSON action block at the tail."
    "Respond in {session_language}."
)

REQUEST_FILE_CONTENT_FOLLOW_UP_USER_MESSAGE = (
    "Check out the result. Brief me through the findings regarding my request specifically. Continue with your actions. Respond in Respond in {session_language}."
)
