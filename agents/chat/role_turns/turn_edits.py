import logging

from core.graph.batch_edits import apply_workflow_edits
from core.schemas.graph_edit_api import (
    ApplyWorkflowEditsResult,
    GraphEdit,
    MultipleEditsSequential,
)
from core.schemas.process_graph import ProcessGraph
from services.logging import setup_colored_logging

logger = setup_colored_logging(logging.DEBUG)


async def set_commenter_and_curator(
    edits: list[GraphEdit],
    *,
    current: ProcessGraph,
    role_id: str,
) -> ApplyWorkflowEditsResult:
    """
    Apply metadata-only edits for the current role.

    The original workflow edits are never passed to apply_workflow_edits.
    Only dedicated set_curator/add_comment edits are created and applied.
    """
    rid = role_id.strip()
    metadata_edits: list[GraphEdit] = []

    if not rid:
        logger.warning(
            "Skipping commenter and curator assignment: role_id is empty"
        )
        return ApplyWorkflowEditsResult(
            attempted=False,
            success=True,
            error=None,
            graph_after=current,
            edits_summary=None,
        )

    for index, edit in enumerate(edits):
        if edit.action == "add_task" and edit.task_id:
            metadata_edit = GraphEdit(
                action="set_curator",
                task_id=edit.task_id,
                curator=rid,
            )
            metadata_edits.append(metadata_edit)

            logger.info(
                "Prepared curator metadata edit: "
                "source_edit_index=%d task_id=%s curator=%s",
                index,
                edit.task_id,
                rid,
            )

        if edit.action == "add_comment" and edit.info:
            metadata_edit = GraphEdit(
                action="add_comment",
                info=edit.info,
                commenter=rid,
            )
            metadata_edits.append(metadata_edit)

            logger.info(
                "Prepared commenter metadata edit: "
                "source_edit_index=%d commenter=%s",
                index,
                rid,
            )

    if not metadata_edits:
        return ApplyWorkflowEditsResult(
            attempted=False,
            success=True,
            error=None,
            graph_after=current,
            edits_summary=None,
        )

    return apply_workflow_edits(
        current=current,
        edits=MultipleEditsSequential(edits=metadata_edits),
    )
