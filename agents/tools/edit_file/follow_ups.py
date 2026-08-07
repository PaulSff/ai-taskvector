"""edit_file tool: follow-up prompt fragments."""

EDIT_FILE_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a file edit. You must check the result.\n\n"
)

EDIT_FILE_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the file edit result for the user if you're done, continue with your work otherwise. "
    "Respond in {session_language}."
)
