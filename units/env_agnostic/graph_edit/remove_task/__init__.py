"""Remove-task edit. See README.md for interface."""
from units.env_agnostic.graph_edit.remove_task.remove_task import (
    EDIT_INPUT_PORTS,
    EDIT_OUTPUT_PORTS,
    register_remove_task,
)

__all__ = ["register_remove_task", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
