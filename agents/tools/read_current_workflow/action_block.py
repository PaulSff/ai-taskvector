
from typing import Literal

from agents.tools.types import ActionBlock


class ReadCurrentWorkflowActionBlock(
    ActionBlock[Literal["read_current_workflow"]]
):
    """Request a summary of the current process graph."""
