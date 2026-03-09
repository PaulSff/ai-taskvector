"""Add-comment edit: add comment. Params: info, commenter?."""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from units.env_agnostic.graph_edit._apply import apply_edit

EDIT_INPUT_PORTS = [("data", "Any"), ("graph", "Any")]
EDIT_OUTPUT_PORTS = [("graph", "Any")]


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    p = params or {}
    edit = {"action": "add_comment", "info": p.get("info"), "commenter": p.get("commenter")}
    return apply_edit(inputs, state, edit)


def register_add_comment() -> None:
    register_unit(UnitSpec(
        type_name="add_comment",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Add comment. Params: info, commenter?.",
    ))


__all__ = ["register_add_comment", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
