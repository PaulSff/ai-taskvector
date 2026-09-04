"""Graph ``edits`` normalization shared by all ``RoleChatHandler`` implementations (before apply / history)."""

from __future__ import annotations

from core.schemas.graph_edit_api import GraphEdit


async def set_commenter_for_new_comments(
    edits: list[GraphEdit],
    *,
    agent_role_id: str,
) -> None:
    """
    For each add_comment edit, set commenter to the trusted chat agent
    role ID in place.
    """
    rid = agent_role_id.strip()
    if not rid:
        return

    for edit in edits:
        if edit.action == "add_comment":
            edit.commenter = rid
