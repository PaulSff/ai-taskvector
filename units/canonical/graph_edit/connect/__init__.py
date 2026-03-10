"""Connect edit. See README.md for interface."""
from units.canonical.graph_edit.connect.connect import (
    EDIT_INPUT_PORTS,
    EDIT_OUTPUT_PORTS,
    register_connect,
)

__all__ = ["register_connect", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
