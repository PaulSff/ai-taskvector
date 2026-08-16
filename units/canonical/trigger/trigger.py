from __future__ import annotations

from copy import deepcopy
from typing import Any

from units.registry import UnitSpec, register_unit

WORKFLOW_TRIGGER_INPUT_PORTS = [("payload", "Any")]
WORKFLOW_TRIGGER_OUTPUT_PORTS = [("payload", "Any"), ("graph", "Any")]


def _trigger_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Build final payload from:
      - params["default_payload"] (base)
      - inputs["payload"] (overrides, if provided and is a dict)
    Then extract graph from final_payload[graph_key] if present.
    """
    graph_key = str(params.get("graph_key", "graph"))

    default_payload = params.get("default_payload", {})
    if not isinstance(default_payload, dict):
        default_payload = {}

    incoming_payload = inputs.get("payload")
    if not isinstance(incoming_payload, dict):
        incoming_payload = {}

    # Start with default payload, then override with incoming payload.
    payload = deepcopy(default_payload)
    payload.update(incoming_payload)

    graph = payload.get(graph_key)

    return ({"payload": payload, "graph": graph}, state)


def register_workflow_trigger() -> None:
    """Register the WorkflowTrigger unit type."""
    register_unit(UnitSpec(
        type_name="WorkflowTrigger",
        input_ports=WORKFLOW_TRIGGER_INPUT_PORTS,
        output_ports=WORKFLOW_TRIGGER_OUTPUT_PORTS,
        step_fn=_trigger_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description=(
            "Entry point for a workflow: forwards merged payload (inputs.payload overriding params.default_payload) "
            "and optional graph (from payload[graph_key])."
        ),
    ))


__all__ = [
    "WORKFLOW_TRIGGER_INPUT_PORTS",
    "WORKFLOW_TRIGGER_OUTPUT_PORTS",
    "register_workflow_trigger",
]
