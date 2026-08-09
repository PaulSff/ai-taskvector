"""read_file tool: follow-up prompt fragments."""

REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a file content. You must check the content.\n\n"
)

REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX = (
    "\n\nInspect the content and address the user's request. If the user wanted to generate a file, output use the corresponding tool to deliver."
    "Respond in {session_language}."
)

REQUEST_FILE_CONTENT_FOLLOW_UP_USER_MESSAGE = (
    "Have you inspected the file content? What is next? Respond in Respond in {session_language}."
)
