"""rename tool: follow-up prompt fragments."""

RENAME_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested renaming a file. You must check the result.\n\n"
)

RENAME_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the file renaming result for the user if you're done, continue with your work otherwise. "
    "Respond in {session_language}."
)
