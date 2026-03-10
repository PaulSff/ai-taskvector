"""Disconnect edit. See README.md for interface."""
from units.canonical.graph_edit.disconnect.disconnect import (
    EDIT_INPUT_PORTS,
    EDIT_OUTPUT_PORTS,
    register_disconnect,
)

__all__ = ["register_disconnect", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
