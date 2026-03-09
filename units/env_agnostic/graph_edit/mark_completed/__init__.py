"""Mark-completed edit. See README.md for interface."""
from units.env_agnostic.graph_edit.mark_completed.mark_completed import (
    EDIT_INPUT_PORTS,
    EDIT_OUTPUT_PORTS,
    register_mark_completed,
)

__all__ = ["register_mark_completed", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
