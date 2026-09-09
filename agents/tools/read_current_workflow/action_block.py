from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from agents.tools.read_current_workflow import run_read_current_workflow_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class ReadCurrentWorkflowActionBlock(
    ActionBlock[Literal["read_current_workflow"]]
):
    """Request a summary of the current process graph."""


def handle_read_current_workflow(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, ReadCurrentWorkflowActionBlock):
        raise TypeError(
            "Expected a read_current_workflow action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "read_current_workflow",
        block.as_json_object(),
    )


def register_read_current_workflow_tool() -> None:
    register_tool(
        "read_current_workflow",
        run_read_current_workflow_follow_up,
        action_blocks={
            "read_current_workflow": ReadCurrentWorkflowActionBlock,
        },
        action_handlers={
            "read_current_workflow": handle_read_current_workflow,
        },
    )


register_read_current_workflow_tool()
