"""Replace-graph edit: replace full graph. Params: units, connections."""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from units.canonical.graph_edit._apply import apply_edit

EDIT_INPUT_PORTS = [("data", "Any"), ("graph", "Any")]
EDIT_OUTPUT_PORTS = [("graph", "Any")]


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    p = params or {}
    edit = {"action": "replace_graph", "units": p.get("units"), "connections": p.get("connections")}
    return apply_edit(inputs, state, edit)


def register_replace_graph() -> None:
    register_unit(UnitSpec(
        type_name="replace_graph",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Replace full graph. Params: units, connections.",
    ))


__all__ = ["register_replace_graph", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
