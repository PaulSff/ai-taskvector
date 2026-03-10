"""Inject unit: forwards initial_inputs as output 'data'. See README.md."""
from units.canonical.inject.inject import (
    INJECT_INPUT_PORTS,
    INJECT_OUTPUT_PORTS,
    register_graph_inject,
    register_inject,
)

__all__ = ["register_inject", "register_graph_inject", "INJECT_INPUT_PORTS", "INJECT_OUTPUT_PORTS"]
