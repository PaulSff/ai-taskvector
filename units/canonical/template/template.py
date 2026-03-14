"""
Template unit: output a fixed value from the "data" param.

Use for debugging or static inputs: set params["data"] in the workflow JSON
and wire the output to Merge, Prompt, or any unit that expects that shape.
No input ports; no initial_inputs required.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

TEMPLATE_INPUT_PORTS: list[tuple[str, str]] = []
TEMPLATE_OUTPUT_PORTS = [("data", "Any")]


def _template_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Output params['data'] on port 'data'. Use for debug/static values."""
    out = params.get("data")
    return ({"data": out}, state)


def register_template() -> None:
    """Register the Template unit type."""
    register_unit(UnitSpec(
        type_name="Template",
        input_ports=TEMPLATE_INPUT_PORTS,
        output_ports=TEMPLATE_OUTPUT_PORTS,
        step_fn=_template_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Output the value of param 'data' (any type). Use for debug or static inputs; wire into Merge/Inject targets.",
    ))


__all__ = [
    "register_template",
    "TEMPLATE_INPUT_PORTS",
    "TEMPLATE_OUTPUT_PORTS",
]
