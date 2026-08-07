"""new_file tool: follow-up prompt fragments."""

MAKE_DIR_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a new folder creation. You must check the result.\n\n"
)

MAKE_DIR_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the result of the new folder creation for the user if you're done, continue with your work otherwise. "
    "Respond in {session_language}."
)
