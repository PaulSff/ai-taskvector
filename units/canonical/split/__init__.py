"""Split unit. See README.md for interface."""
from units.canonical.split.split import (
    SPLIT_INPUT_PORTS,
    SPLIT_OUTPUT_PORTS,
    register_split,
)

__all__ = ["SPLIT_INPUT_PORTS", "SPLIT_OUTPUT_PORTS", "register_split"]
