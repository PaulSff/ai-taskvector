"""Trigger unit: entry point for a workflow; forwards initial_inputs to Merge and Process."""
from units.env_agnostic.trigger.trigger import (
    WORKFLOW_TRIGGER_INPUT_PORTS,
    WORKFLOW_TRIGGER_OUTPUT_PORTS,
    register_workflow_trigger,
)

__all__ = [
    "register_workflow_trigger",
    "WORKFLOW_TRIGGER_INPUT_PORTS",
    "WORKFLOW_TRIGGER_OUTPUT_PORTS",
]
