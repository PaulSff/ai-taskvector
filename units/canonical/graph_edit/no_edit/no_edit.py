"""No-edit: pass-through; output graph unchanged. Params: reason?."""
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
    edit = {"action": "no_edit", "reason": (params or {}).get("reason")}
    return apply_edit(inputs, state, edit)


def register_no_edit() -> None:
    register_unit(UnitSpec(
        type_name="no_edit",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="No-op; output graph unchanged. Params: reason?.",
    ))


__all__ = ["register_no_edit", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
