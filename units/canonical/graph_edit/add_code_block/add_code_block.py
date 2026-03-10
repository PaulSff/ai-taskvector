"""Add-code-block edit: add code block. Params: code_block (id, source, language?)."""
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
    edit = {"action": "add_code_block", "code_block": (params or {}).get("code_block")}
    return apply_edit(inputs, state, edit)


def register_add_code_block() -> None:
    register_unit(UnitSpec(
        type_name="add_code_block",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Add code block. Params: code_block (id, source, language?).",
    ))


__all__ = ["register_add_code_block", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
