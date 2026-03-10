"""GraphSummary unit: graph → summary dict."""
from units.canonical.graph_summary.graph_summary import (
    GRAPH_SUMMARY_INPUT_PORTS,
    GRAPH_SUMMARY_OUTPUT_PORTS,
    register_graph_summary,
)

__all__ = [
    "register_graph_summary",
    "GRAPH_SUMMARY_INPUT_PORTS",
    "GRAPH_SUMMARY_OUTPUT_PORTS",
]
