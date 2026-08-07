"""new_file tool: follow-up prompt fragments."""

NEW_FILE_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a new file creation. You must check the result.\n\n"
)

NEW_FILE_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the result for the user if you're done, continue with your work otherwise. "
    "Respond in {session_language}."
)
