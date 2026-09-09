from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_action_block, register_tool
from agents.tools.types import ActionBlock, ParsedActions

WorkflowOrigin = Literal[
    "node-red",
    "n8n",
    "dict",
    "canonical",
    "pyflow",
    "comfyui",
    "ryven",
    "idaes",
]

MergeValue = Literal["true", "false"]


class ImportWorkflowActionBlock(
    ActionBlock[Literal["import_workflow"]]
):
    """Load a workflow from the knowledge base or a URL."""

    source: str
    origin: WorkflowOrigin
    merge: MergeValue | None = None

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("source must not be empty")

        return value


def handle_import_workflow(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, ImportWorkflowActionBlock):
        raise TypeError(
            "Expected an import_workflow action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "import_workflow",
        block.as_json_object(),
    )


"""
def register_import_workflow_tool() -> None:
    register_tool(
        "import_workflow",
        run_import_workflow_follow_up,
        action_blocks={
            "import_workflow": ImportWorkflowActionBlock,
        },
        action_handlers={
            "import_workflow": handle_import_workflow,
        },
    )


register_import_workflow_tool()

"""
