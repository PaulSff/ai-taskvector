"""
Inject unit: forwards any valid structure (JSON/dict) from initial_inputs as a single output.
Env-agnostic; any unit can use it for data injection (edit flows: graph; assistant flows: context;
subflows: inject a nested/subflow to be merged or run downstream).
The executor must pass initial_inputs[inject_unit_id] = { ... } with any valid dict structure.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

INJECT_INPUT_PORTS: list[tuple[str, str]] = []
INJECT_OUTPUT_PORTS = [("data", "Any")]


def _inject_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Forward the full payload from initial_inputs; any valid dict/JSON structure
    data = dict(inputs) if inputs else {}
    return ({"data": data}, state)


def register_graph_inject() -> None:
    register_unit(UnitSpec(
        type_name="graph_inject",
        input_ports=INJECT_INPUT_PORTS,
        output_ports=INJECT_OUTPUT_PORTS,
        step_fn=_inject_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Forward any valid JSON/dict from initial_inputs as output 'data'. E.g. graph, full context, or a subflow to inject.",
    ))


__all__ = ["register_graph_inject", "INJECT_INPUT_PORTS", "INJECT_OUTPUT_PORTS"]
