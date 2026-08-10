"""edit_file tool: follow-up prompt fragments."""

EDIT_FILE_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a file edit. You must check the result.\n\n"
)

EDIT_FILE_FOLLOW_UP_SUFFIX = (
    "\n\n Summarize the result. Was your edit succesful? If not, correct yourself, and give it another try. "
    "Respond in {session_language}."
)
