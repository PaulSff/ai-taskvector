"""
Load chat history from file: parse payload and produce session data for the UI to apply.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast


def load_chat_session(
    path: Path,
    *,
    load_payload: Callable[[Path], dict[str, object] | None],
    new_id: Callable[[], str],
    now_ts: Callable[[], str],
) -> dict[str, object] | None:
    """
    Load and parse chat payload from path.
    Returns session dict (messages, session_id, created_at, agent_selected, has_sent_any)
    or None if load failed.
    """
    payload = load_payload(path)
    if payload is None:
        return None

    # Narrow 'messages' from object -> list[object]
    raw_msgs = payload.get("messages")
    msgs: list[object] = []
    if isinstance(raw_msgs, list):
        # Cast raw_msgs from list[Unknown] to list[object]
        msgs = cast(list[object], raw_msgs)


    # Strict check for has_sent_any
    sent_any = False
    for m in msgs:
        if isinstance(m, dict):
            # FIX: Cast the dict to remove the "Unknown" status
            m_typed = cast(dict[str, object], m)

            # Now .get() returns 'object | None' instead of 'Unknown | None'
            role = m_typed.get("role")
            content = m_typed.get("content")

            # Now we narrow 'object' to 'str'
            role_str = role if isinstance(role, str) else ""
            content_str = content if isinstance(content, str) else ""

            if role_str == "user" and content_str.strip():
                sent_any = True
                break


    return {
        "messages": msgs,
        "session_id": str(payload.get("session_id") or new_id()),
        "created_at": str(payload.get("created_at") or now_ts()),
        "agent_selected": payload.get("agent_selected"),
        "session_language": str(payload.get("session_language") or ""),
        "has_sent_any": sent_any,
    }

# --- Helpers ---
def _history_dedupe_prefer_applied(
    history: list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    if not history:
        return []

    # best_by_content: mapping content string to the dictionary object
    best_by_content: dict[str, dict[str, object]] = {}
    rank_by_content: dict[str, int] = {}

    for m in history:
        # Narrow m.get("content") to str
        raw_content = m.get("content")
        content = (raw_content if isinstance(raw_content, str) else "").strip()

        if not content:
            continue

        result_kind: str | None = None

        # Get the workflow response
        wf_res = m.get("workflow_response")

        if isinstance(wf_res, dict):
            wf_res_typed = cast(dict[str, object], wf_res)

            # Now .get() returns 'object | None'
            kind = wf_res_typed.get("result_kind")

            if isinstance(kind, str):
                result_kind = kind


        rank = 1 if result_kind == "applied" else 0

        prev_rank = rank_by_content.get(content, -1)
        if content not in best_by_content or rank > prev_rank:
            best_by_content[content] = m
            rank_by_content[content] = rank

    # Preserve original order for the kept messages
    seen_content: set[str] = set()
    out: list[dict[str, object]] = []
    for m in history:
        raw_content = m.get("content")
        content = (raw_content if isinstance(raw_content, str) else "").strip()

        if not content or content in seen_content:
            continue

        kept = best_by_content.get(content)
        if kept is m:
            out.append(m)
            seen_content.add(content)

    return out
