"""Switch unit. See README.md for interface."""
from units.canonical.switch.switch import (
    SWITCH_INPUT_PORTS,
    SWITCH_OUTPUT_PORTS,
    register_switch,
)

__all__ = ["SWITCH_INPUT_PORTS", "SWITCH_OUTPUT_PORTS", "register_switch"]
