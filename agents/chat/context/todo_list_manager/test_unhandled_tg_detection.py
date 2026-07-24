"""Standalone test: detect unhandled TG chats from tg_messages*.json.

Run from repo root:
    python gui/chat/context/todo_list_manager/test_unhandled_tg_detection.py [messages_dir]
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE = "Respond to the incoming message: "


def _latest_tg_messages_file(messages_dir: str) -> str | None:
    if not messages_dir or not os.path.isdir(messages_dir):
        return None
    candidates = [
        os.path.join(messages_dir, f)
        for f in os.listdir(messages_dir)
        if f.startswith("tg_messages") and f.endswith(".json")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: os.path.getmtime(p))


def load_tg_history(messages_dir: str) -> list[dict[str, Any]]:
    path = _latest_tg_messages_file(messages_dir)
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [m for m in data if isinstance(m, dict)]
    if isinstance(data, dict):
        by_chat = data.get("messages_by_chat_id")
        if isinstance(by_chat, dict):
            history: list[dict[str, Any]] = []
            for msgs in by_chat.values():
                if isinstance(msgs, list):
                    history.extend(m for m in msgs if isinstance(m, dict))
            return history
    return []


def extract_message_text(m: dict[str, Any]) -> str:
    if m.get("content", {}).get("@type") == "messageText":
        return str((m.get("content", {}).get("text", {}) or {}).get("text") or "")
    return str(
        (m.get("content", {}).get("text", {}) or {}).get("text") or m.get("text") or ""
    ).strip()


def detect_unhandled_chats(history: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    by_chat: dict[str, dict[str, Any]] = {}
    for m in history:
        chat_id = m.get("chat_id")
        if chat_id is None:
            continue
        cid = str(chat_id)
        prev = by_chat.get(cid)
        if prev is None or (m.get("date") or 0) >= (prev.get("date") or 0):
            by_chat[cid] = m

    pending: list[dict] = []
    responded: list[dict] = []
    for cid, last_msg in by_chat.items():
        from_id = (last_msg.get("from") or {}).get("id")
        if from_id is None:
            continue
        entry = {
            "chat_id": cid,
            "message_id": last_msg.get("id"),
            "text": extract_message_text(last_msg),
            "date": last_msg.get("date"),
        }
        if str(from_id) == cid:
            pending.append(entry)
        else:
            responded.append(entry)
    return pending, responded


def main() -> int:
    messages_dir = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(os.path.dirname(__file__), "../../../mydata/tg_messages")
    )
    messages_dir = os.path.abspath(messages_dir)
    latest = _latest_tg_messages_file(messages_dir)

    print(f"Messages dir: {messages_dir}")
    print(f"Latest file:    {latest}")

    history = load_tg_history(messages_dir)
    print(f"Loaded messages: {len(history)}")

    pending, responded = detect_unhandled_chats(history)
    print(f"\nPending (unhandled) chats: {len(pending)}")
    for p in pending:
        preview = (p["text"] or "")[:70]
        print(
            f"  chat_id={p['chat_id']} msg_id={p['message_id']} "
            f"date={p['date']} text={preview!r}"
        )

    print(f"\nResponded chats: {len(responded)}")
    for r in responded:
        preview = (r["text"] or "")[:70]
        print(
            f"  chat_id={r['chat_id']} msg_id={r['message_id']} "
            f"date={r['date']} text={preview!r}"
        )

    if not pending and not responded:
        print("\nFAIL: no chats detected (check file format / path)")
        return 1

    print(f"\nOK: would queue {len(pending)} reply-to task(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
