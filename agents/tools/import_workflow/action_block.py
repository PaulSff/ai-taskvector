
from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock

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
