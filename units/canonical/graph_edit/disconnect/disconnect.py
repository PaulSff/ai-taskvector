"""Disconnect edit: disconnect two units. Params: from_id, to_id, from_port?, to_port?."""
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
    edit = {
        "action": "disconnect",
        "from": p.get("from_id") or p.get("from"),
        "to": p.get("to_id") or p.get("to"),
        "from_port": p.get("from_port"),
        "to_port": p.get("to_port"),
    }
    return apply_edit(inputs, state, edit)


def register_disconnect() -> None:
    register_unit(UnitSpec(
        type_name="disconnect",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Disconnect two units. Params: from_id, to_id, from_port?, to_port?.",
    ))


__all__ = ["register_disconnect", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
