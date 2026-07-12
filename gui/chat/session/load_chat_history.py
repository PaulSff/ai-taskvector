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
    Returns session dict (messages, session_id, created_at, agent_selected, has_sent_any)
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
        "agent_selected": payload.get("agent_selected"),
        "session_language": str(payload.get("session_language") or ""),
        "has_sent_any": has_sent_any,
    }

# --- Helpers ---
def _history_dedupe_prefer_applied(
    history: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not history:
        return []

    # For each content, pick the best candidate (applied > non-applied).
    best_by_content: dict[str, dict[str, Any]] = {}
    rank_by_content: dict[str, int] = {}

    for m in history:
        content = (m.get("content") or "").strip()
        if not content:
            # Keep empty streaming/start markers out of preview to avoid clutter/dup.
            # Remove this block if you actually want empties shown.
            continue

        result_kind = (
            (m.get("workflow_response") or {}).get("result_kind")
            if isinstance(m.get("workflow_response"), dict)
            else None
        )

        rank = 1 if result_kind == "applied" else 0

        prev_rank = rank_by_content.get(content, -1)
        if content not in best_by_content or rank > prev_rank:
            best_by_content[content] = m
            rank_by_content[content] = rank

    # Preserve original order for the kept messages
    seen_content: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in history:
        content = (m.get("content") or "").strip()
        if not content or content in seen_content:
            continue
        kept = best_by_content.get(content)
        if kept is m:
            out.append(m)
            seen_content.add(content)

    return out
