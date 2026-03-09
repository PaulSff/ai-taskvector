"""Add-todo-list edit: add todo list. Params: title?."""
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
    edit = {"action": "add_todo_list", "title": (params or {}).get("title")}
    return apply_edit(inputs, state, edit)


def register_add_todo_list() -> None:
    register_unit(UnitSpec(
        type_name="add_todo_list",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Add todo list. Params: title?.",
    ))


__all__ = ["register_add_todo_list", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
