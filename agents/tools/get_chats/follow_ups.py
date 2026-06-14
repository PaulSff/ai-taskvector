"""get_chats tool: follow-up prompt fragments."""

from agents.tools.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

GET_CHATS_FOLLOW_UP_PREFIX = (
    "IMPORTANT: Unread chat messages from your previous turn.\n\n"
)
GET_CHATS_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
GET_CHATS_FOLLOW_UP_USER_MESSAGE = "You have new unread messages to handle. Check the unread messages. Respond in {session_language}."
