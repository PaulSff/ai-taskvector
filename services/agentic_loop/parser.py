import json

from agents.chat.context.todo_list_manager.prompts import (
    TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE,
)


def extract_chat_id_from_task_text(text: str) -> str | None:
    """
    Extract all system tasks, which are set to handle a specific unread chat.
    """
    if not text.startswith(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):
        return None

    payload_text = text[len(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):].strip()

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None

    chat_id = payload.get("chat_id")
    return str(chat_id).strip() if chat_id is not None else None
