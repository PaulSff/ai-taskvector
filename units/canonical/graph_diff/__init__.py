"""GraphDiff unit: prev_graph + current_graph → diff string."""
from units.canonical.graph_diff.graph_diff import (
    GRAPH_DIFF_INPUT_PORTS,
    GRAPH_DIFF_OUTPUT_PORTS,
    register_graph_diff,
)

__all__ = [
    "register_graph_diff",
    "GRAPH_DIFF_INPUT_PORTS",
    "GRAPH_DIFF_OUTPUT_PORTS",
]
