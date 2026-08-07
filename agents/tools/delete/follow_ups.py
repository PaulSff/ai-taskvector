"""delete tool: follow-up prompt fragments."""

DELETE_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested delete action. You must check the result.\n\n"
)

DELETE_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the deletion result for the user if you're done, continue with your work otherwise. "
    "Respond in {session_language}."
)
