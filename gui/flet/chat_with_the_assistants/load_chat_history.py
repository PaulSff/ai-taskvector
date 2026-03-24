"""
Load chat history from file: parse payload and produce session data for the UI to apply.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def load_chat_session(
    path: Path,
    *,
    load_payload: Callable[[Path], dict[str, Any] | None],
    new_id: Callable[[], str],
    now_ts: Callable[[], str],
) -> dict[str, Any] | None:
    """
    Load and parse chat payload from path.
    Returns session dict (messages, session_id, created_at, assistant_selected, has_sent_any)
    or None if load failed.
    """
    payload = load_payload(path)
    if payload is None:
        return None

    msgs = payload.get("messages")
    if not isinstance(msgs, list):
        msgs = []

    has_sent_any = any(
        m.get("role") == "user" and (m.get("content") or "").strip()
        for m in msgs
        if isinstance(m, dict)
    )

    return {
        "messages": msgs,
        "session_id": str(payload.get("session_id") or new_id()),
        "created_at": str(payload.get("created_at") or now_ts()),
        "assistant_selected": payload.get("assistant_selected"),
        "session_language": str(payload.get("session_language") or ""),
        "has_sent_any": has_sent_any,
    }
