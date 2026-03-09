"""
Graph inject unit: outputs the graph provided as initial_inputs (for edit flows).
Env-agnostic; used at the start of edit workflows (Inject -> add_unit -> ...).
The executor must pass initial_inputs[inject_unit_id] = {"graph": current_graph}.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

GRAPH_INJECT_INPUT_PORTS: list[tuple[str, str]] = []
GRAPH_INJECT_OUTPUT_PORTS = [("graph", "Any")]


def _graph_inject_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = inputs.get("graph")
    if graph is None:
        graph = {}
    return ({"graph": graph}, state)


def register_graph_inject() -> None:
    register_unit(UnitSpec(
        type_name="graph_inject",
        input_ports=GRAPH_INJECT_INPUT_PORTS,
        output_ports=GRAPH_INJECT_OUTPUT_PORTS,
        step_fn=_graph_inject_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Output the graph from initial_inputs (for edit flows). No inputs from connections.",
    ))


__all__ = ["register_graph_inject", "GRAPH_INJECT_INPUT_PORTS", "GRAPH_INJECT_OUTPUT_PORTS"]
