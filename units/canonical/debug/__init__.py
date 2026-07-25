"""Debug unit: log input to workflow.log and pass through."""

from units.canonical.debug.debug import (
    DEBUG_INPUT_PORTS,
    DEBUG_OUTPUT_PORTS,
    register_debug,
)

__all__ = ["DEBUG_INPUT_PORTS", "DEBUG_OUTPUT_PORTS", "register_debug"]
