"""Telegram gateway prompt lines"""


GET_CHATS_FOLLOW_UP_USER_MESSAGE_TEMPLATE = (
    "You have new incoming messages to handle. "
    "First, use the send_message action to reply briefly to each, then leverage additional actions if needed (e.g. if web_search, read-file is required to accomplish the goal). Share the summary over telegram using the same chat_id, once finished. "
    "Unread messages: {unread_chats}."
)
