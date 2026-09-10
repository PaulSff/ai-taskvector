import logging

from core.schemas.graph_edit_api import GraphEdit
from services.logging import setup_colored_logging

logger = setup_colored_logging(logging.DEBUG)


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
        logger.warning(
            "Skipping commenter assignment: agent_role_id is empty"
        )
        return

    for index, edit in enumerate(edits):
        if edit.action != "add_comment":
            continue

        edit.commenter = rid

        logger.info(
            "Set commenter for new comment: "
            "edit_index=%d comment_id=%s commenter=%s info=%r",
            index,
            edit.id,
            rid,
            edit.info,
        )
