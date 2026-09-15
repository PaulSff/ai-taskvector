"""Replace-graph edit: replace full graph. Params: units, connections."""
from __future__ import annotations

from core.schemas.primitives import Data, Output
from units.canonical.graph_edit._apply import apply_edit
from units.registry import UnitSpec, register_unit

EDIT_INPUT_PORTS = [("data", "Any"), ("graph", "Any")]
EDIT_OUTPUT_PORTS = [("graph", "Any")]


def _step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
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


__all__ = ["EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS", "register_replace_graph"]
