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
    # If initial_inputs[unit_id] has key "data", forward that value; else forward full payload.
    payload = dict(inputs) if inputs else {}
    out = payload.get("data", payload)
    return ({"data": out}, state)


def register_inject() -> None:
    """Register the Inject unit type."""
    register_unit(UnitSpec(
        type_name="Inject",
        input_ports=INJECT_INPUT_PORTS,
        output_ports=INJECT_OUTPUT_PORTS,
        step_fn=_inject_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Forward any valid JSON/dict from initial_inputs as output 'data'. E.g. graph, full context, or a subflow to inject.",
    ))


# Backward-compatible alias
def register_graph_inject() -> None:
    """Register the Inject unit type (alias for register_inject)."""
    register_inject()


__all__ = ["register_inject", "register_graph_inject", "INJECT_INPUT_PORTS", "INJECT_OUTPUT_PORTS"]
