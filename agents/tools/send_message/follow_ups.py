"""send_message tool: follow-up prompt fragments."""

from agents.tools.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

SEND_MESSAGE_FOLLOW_UP_PREFIX = (
    "IMPORTANT: Message status from your previous turn.\n\n"
)
SEND_MESSAGE_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
SEND_MESSAGE_FOLLOW_UP_USER_MESSAGE = (
    "Check the message status. If the message was not sent, try sending it again if suitable."
)
