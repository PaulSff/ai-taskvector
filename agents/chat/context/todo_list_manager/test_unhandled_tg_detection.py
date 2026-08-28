"""Standalone test: detect unhandled TG chats from tg_messages*.json.

Run from repo root:
    python agents/chat/context/todo_list_manager/test_unhandled_tg_detection.py [messages_dir]
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE = (
    "Respond to the incoming message: "
)


def _latest_tg_messages_file(messages_dir: str) -> str | None:
    if not messages_dir or not os.path.isdir(messages_dir):
        return None

    candidates = [
        os.path.join(messages_dir, filename)
        for filename in os.listdir(messages_dir)
        if filename.startswith("tg_messages")
        and filename.endswith(".json")
    ]

    if not candidates:
        return None

    return max(candidates, key=lambda path: os.path.getmtime(path))


def load_tg_history(messages_dir: str) -> list[dict[str, Any]]:
    path = _latest_tg_messages_file(messages_dir)

    if not path:
        return []

    with open(path, encoding="utf-8") as f:
        data: object = json.load(f)

    if isinstance(data, list):
        return [
            message
            for message in data
            if isinstance(message, dict)
        ]

    if isinstance(data, dict):
        by_chat = data.get("messages_by_chat_id")

        if isinstance(by_chat, dict):
            history: list[dict[str, Any]] = []

            for messages in by_chat.values():
                if not isinstance(messages, list):
                    continue

                history.extend(
                    message
                    for message in messages
                    if isinstance(message, dict)
                )

            return history

    return []


def extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")

    if isinstance(content, dict):
        if content.get("@type") == "messageText":
            text_data = content.get("text")

            if isinstance(text_data, dict):
                return str(text_data.get("text") or "")

        text_data = content.get("text")

        if isinstance(text_data, dict):
            content_text = text_data.get("text")

            if content_text:
                return str(content_text).strip()

    return str(message.get("text") or "").strip()


def detect_unhandled_chats(
    history: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_chat: dict[str, dict[str, Any]] = {}

    for message in history:
        chat_id = message.get("chat_id")

        if chat_id is None:
            continue

        chat_id_str = str(chat_id)
        previous_message = by_chat.get(chat_id_str)

        if previous_message is None:
            by_chat[chat_id_str] = message
            continue

        current_date = message.get("date") or 0
        previous_date = previous_message.get("date") or 0

        if current_date >= previous_date:
            by_chat[chat_id_str] = message

    pending: list[dict[str, Any]] = []
    responded: list[dict[str, Any]] = []

    for chat_id, last_message in by_chat.items():
        raw_from = last_message.get("from")

        if not isinstance(raw_from, dict):
            continue

        from_id = raw_from.get("id")

        if from_id is None:
            continue

        entry: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": last_message.get("id"),
            "text": extract_message_text(last_message),
            "date": last_message.get("date"),
        }

        if str(from_id) == chat_id:
            pending.append(entry)
        else:
            responded.append(entry)

    return pending, responded


def main() -> int:
    messages_dir = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(
            os.path.dirname(__file__),
            "../../../mydata/tg_messages",
        )
    )

    messages_dir = os.path.abspath(messages_dir)
    latest = _latest_tg_messages_file(messages_dir)

    print(f"Messages dir: {messages_dir}")
    print(f"Latest file:    {latest}")

    history = load_tg_history(messages_dir)
    print(f"Loaded messages: {len(history)}")

    pending, responded = detect_unhandled_chats(history)

    print(f"\nPending (unhandled) chats: {len(pending)}")

    for pending_chat in pending:
        preview = str(pending_chat.get("text") or "")[:70]

        print(
            f"  chat_id={pending_chat.get('chat_id')} "
            + f"msg_id={pending_chat.get('message_id')} "
            + f"date={pending_chat.get('date')} "
            + f"text={preview!r}"
        )

    print(f"\nResponded chats: {len(responded)}")

    for responded_chat in responded:
        preview = str(responded_chat.get("text") or "")[:70]

        print(
            f"  chat_id={responded_chat.get('chat_id')} "
            + f"msg_id={responded_chat.get('message_id')} "
            + f"date={responded_chat.get('date')} "
            + f"text={preview!r}"
        )

    if not pending and not responded:
        print("\nFAIL: no chats detected (check file format / path)")
        return 1

    print(f"\nOK: would queue {len(pending)} reply-to task(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
