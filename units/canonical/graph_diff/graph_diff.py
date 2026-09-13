"""
GraphDiff unit: prev_graph + current_graph → compact diff string.

Inputs: prev_graph (ProcessGraph), current_graph (ProcessGraph).
Output: diff (str) — changelog of added/removed units and connections.
Used in the agent workflow so the runner does not need to compute diff; the workflow provides recent_changes_block from this unit.
"""

from __future__ import annotations

from core.graph.diff import graph_diff as _graph_diff
from core.schemas import ProcessGraph
from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

GRAPH_DIFF_INPUT_PORTS = [("prev_graph", "ProcessGraph"), ("current_graph", "ProcessGraph")]
GRAPH_DIFF_OUTPUT_PORTS = [("diff", "str")]


def _as_graph(value: object) -> ProcessGraph | None:
    if value is None:
        return None

    if isinstance(value, ProcessGraph):
        return value

    if isinstance(value, dict):
        return ProcessGraph.model_validate(value)

    raise TypeError(
        f"Expected ProcessGraph, mapping, or None; got {type(value).__name__}"
    )

def _graph_diff_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Compute the structured diff between the previous and current graphs."""
    prev = _as_graph(inputs.get("prev_graph"))
    current = _as_graph(inputs.get("current_graph"))

    diff = _graph_diff(prev, current, format="payload")

    return {"diff": diff}, state


def register_graph_diff() -> None:
    """Register the GraphDiff unit type."""
    register_unit(
        UnitSpec(
            type_name="GraphDiff",
            input_ports=GRAPH_DIFF_INPUT_PORTS,
            output_ports=GRAPH_DIFF_OUTPUT_PORTS,
            step_fn=_graph_diff_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="Computes compact changelog (added/removed units and connections) between prev and current graph.",
        )
    )


__all__ = ["GRAPH_DIFF_INPUT_PORTS", "GRAPH_DIFF_OUTPUT_PORTS", "register_graph_diff"]
