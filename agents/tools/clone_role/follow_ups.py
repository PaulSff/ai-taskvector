"""clone_role tool: follow-up prompt fragments."""

CLONE_ROLE_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the clone_role action. You must check the results below and share it with the user. Avoid greetings, you already said hello to the user last turn.\n\n"
)

CLONE_ROLE_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the clone_role output for the user, check if it meets the requirements. Quote and interpret the result. "
    "Respond in {session_language}."
)

CLONE_ROLE_FOLLOW_UP_USER_MESSAGE = (
    "Please, check the role clonning status."
)
