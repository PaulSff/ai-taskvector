"""
GraphDiff unit: prev_graph + current_graph → compact diff string.

Inputs: prev_graph (Any), current_graph (Any).
Output: diff (str) — changelog of added/removed units and connections.
Used in the assistant workflow so the runner does not need to compute diff; the workflow provides recent_changes_block from this unit.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from core.graph.diff import graph_diff as _graph_diff

GRAPH_DIFF_INPUT_PORTS = [("prev_graph", "Any"), ("current_graph", "Any")]
GRAPH_DIFF_OUTPUT_PORTS = [("diff", "str")]


def _graph_diff_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute diff between prev and current graph."""
    prev = inputs.get("prev_graph")
    current = inputs.get("current_graph")
    diff = _graph_diff(prev, current)
    return ({"diff": diff}, state)


def register_graph_diff() -> None:
    """Register the GraphDiff unit type."""
    register_unit(UnitSpec(
        type_name="GraphDiff",
        input_ports=GRAPH_DIFF_INPUT_PORTS,
        output_ports=GRAPH_DIFF_OUTPUT_PORTS,
        step_fn=_graph_diff_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Computes compact changelog (added/removed units and connections) between prev and current graph.",
    ))


__all__ = ["register_graph_diff", "GRAPH_DIFF_INPUT_PORTS", "GRAPH_DIFF_OUTPUT_PORTS"]
