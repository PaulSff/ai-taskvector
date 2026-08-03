"""Remove-unit edit. See README.md for interface."""
from units.canonical.graph_edit.remove_unit.remove_unit import (
    EDIT_INPUT_PORTS,
    EDIT_OUTPUT_PORTS,
    register_remove_unit,
)

__all__ = ["EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS", "register_remove_unit"]
