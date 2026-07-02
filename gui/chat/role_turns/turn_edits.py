"""Graph ``edits`` normalization shared by all ``RoleChatHandler`` implementations (before apply / history)."""

from __future__ import annotations

from typing import Any


async def canonicalize_add_comment_edits(edits: Any, *, agent_role_id: str) -> None:
    """
    For each ``add_comment`` edit, set ``commenter`` to the trusted chat agent role id (in place).

    Call on ``result["edits"]`` (or any edit list) for every role that can emit graph edits from the main chat.
    """
    rid = (agent_role_id or "").strip()
    if not rid or not isinstance(edits, list):
        return
    for e in edits:
        if isinstance(e, dict) and (e.get("action") or "").strip() == "add_comment":
            e["commenter"] = rid
