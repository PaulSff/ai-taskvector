"""Add-pipeline edit: add pipeline (RLGym, RLOracle, etc.). Params: pipeline (id, type, params)."""
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
    edit = {"action": "add_pipeline", "pipeline": (params or {}).get("pipeline")}
    return apply_edit(inputs, state, edit)


def register_add_pipeline() -> None:
    register_unit(UnitSpec(
        type_name="add_pipeline",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Add pipeline (RLGym, RLOracle, etc.). Params: pipeline (id, type, params).",
    ))


__all__ = ["register_add_pipeline", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
