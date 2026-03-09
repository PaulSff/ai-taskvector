"""Mark-completed edit: mark task completed. Params: task_id, completed?."""
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
    edit = {"action": "mark_completed", "task_id": p.get("task_id"), "completed": p.get("completed", True)}
    return apply_edit(inputs, state, edit)


def register_mark_completed() -> None:
    register_unit(UnitSpec(
        type_name="mark_completed",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Mark task completed. Params: task_id, completed?.",
    ))


__all__ = ["register_mark_completed", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
