"""Replace-unit edit: replace unit. Params: find_unit, replace_with."""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from units.env_agnostic.graph_edit._apply import apply_edit

EDIT_INPUT_PORTS = [("graph", "Any")]
EDIT_OUTPUT_PORTS = [("graph", "Any")]


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    p = params or {}
    edit = {"action": "replace_unit", "find_unit": p.get("find_unit"), "replace_with": p.get("replace_with")}
    return apply_edit(inputs, state, edit)


def register_replace_unit() -> None:
    register_unit(UnitSpec(
        type_name="replace_unit",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Replace unit. Params: find_unit, replace_with.",
    ))


__all__ = ["register_replace_unit", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
