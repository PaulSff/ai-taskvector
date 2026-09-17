"""edit_file tool: follow-up prompt fragments."""

EDIT_FILE_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the file edit on the prevous turn. You must check the result:\n\n"
)

EDIT_FILE_FOLLOW_UP_SUFFIX = (
    "\n\n Summarize the result above. In case of any error taking place, correct yourself, then give it another try. "
    "Respond in {session_language}."
)
