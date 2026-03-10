"""
Trigger unit: single entry point for a workflow.

Receives a payload dict from the runner via initial_inputs["trigger"]["payload"] and
forwards it; optionally forwards a graph extracted from the payload (key configurable via params).
No hardcoded payload keys; the runner defines the payload shape.
"""
from __future__ import annotations

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
    """Forward payload; extract graph from payload[graph_key] if present."""
    payload = inputs.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    graph_key = str(params.get("graph_key", "graph"))
    graph = payload.get(graph_key) if payload else None
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
        description="Entry point for a workflow: forwards payload and optional graph (from payload[graph_key]).",
    ))


__all__ = [
    "register_workflow_trigger",
    "WORKFLOW_TRIGGER_INPUT_PORTS",
    "WORKFLOW_TRIGGER_OUTPUT_PORTS",
]
