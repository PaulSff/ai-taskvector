"""
Load chat history from file: parse payload and produce session data for the UI to apply.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from core.schemas.primitives import Data

from .state import AgentChatHistory


def load_chat_session(
    path: Path,
    *,
    load_payload: Callable[[Path], Data | None],
    new_id: Callable[[], str],
    now_ts: Callable[[], str],
) -> Data | None:
    """
    Load and parse chat payload from path.
    Returns session dict (messages, session_id, created_at, agent_selected, has_sent_any)
    or None if load failed.
    """
    payload = load_payload(path)
    if payload is None:
        return None

    raw_msgs = payload.get("messages")
    msgs: list[object] = raw_msgs if isinstance(raw_msgs, list) else []

    sent_any = False
    for m in msgs:
        if not isinstance(m, dict):
            continue

        role = m.get("role")
        content = m.get("content")

        if isinstance(role, str) and isinstance(content, str) and role == "user" and content.strip():
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
def history_dedupe_prefer_applied(
    history: AgentChatHistory | None,
) -> AgentChatHistory:
    if not history:
        return []

    best_by_content: dict[str, Data] = {}
    rank_by_content: dict[str, int] = {}

    for m in history:
        raw_content = m.get("content")
        content = (raw_content if isinstance(raw_content, str) else "").strip()
        if not content:
            continue

        result_kind: str | None = None

        wf_res = m.get("workflow_response")
        if isinstance(wf_res, dict):
            kind = wf_res.get("result_kind")
            if isinstance(kind, str):
                result_kind = kind

        rank = 1 if result_kind == "applied" else 0
        prev_rank = rank_by_content.get(content, -1)

        if content not in best_by_content or rank > prev_rank:
            best_by_content[content] = m
            rank_by_content[content] = rank

    seen_content: set[str] = set()
    out: AgentChatHistory = []
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
