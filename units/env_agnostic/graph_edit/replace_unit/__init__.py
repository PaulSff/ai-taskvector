"""Replace-unit edit. See README.md for interface."""
from units.env_agnostic.graph_edit.replace_unit.replace_unit import (
    EDIT_INPUT_PORTS,
    EDIT_OUTPUT_PORTS,
    register_replace_unit,
)

__all__ = ["register_replace_unit", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
