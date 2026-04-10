"""read_code_block skill: follow-up prompt fragments."""

from assistants.skills.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

READ_CODE_BLOCK_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested code block(s) from the graph. You must check the code.\n\n"
)
READ_CODE_BLOCK_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE = (
    "Check out the code blocks in either the graph summary or Knowledge base excerpts: {unit_ids}. Keep going with your edits."
    "Respond in {session_language}."
)
