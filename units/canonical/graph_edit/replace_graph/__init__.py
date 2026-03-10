"""Replace-graph edit. See README.md for interface."""
from units.canonical.graph_edit.replace_graph.replace_graph import (
    EDIT_INPUT_PORTS,
    EDIT_OUTPUT_PORTS,
    register_replace_graph,
)

__all__ = ["register_replace_graph", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
