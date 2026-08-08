"""read_file tool: follow-up prompt fragments."""

REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a file content. You must check the content.\n\n"
)

REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX = (
    "\n\nIf the user requested a summary/report/readme as a file, use the `report` action to deliver right away. Summarize the content otherwise."
    "Respond in {session_language}."
)
