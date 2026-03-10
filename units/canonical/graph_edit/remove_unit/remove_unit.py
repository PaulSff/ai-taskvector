"""Remove-unit edit: remove unit. Params: unit_id."""
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
    edit = {"action": "remove_unit", "unit_id": (params or {}).get("unit_id")}
    return apply_edit(inputs, state, edit)


def register_remove_unit() -> None:
    register_unit(UnitSpec(
        type_name="remove_unit",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Remove unit. Params: unit_id.",
    ))


__all__ = ["register_remove_unit", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
