"""
Assistants: apply structured edits → normalizer → canonical graph/config.
Workflow Designer: graph edits (add/remove/connect) → ProcessGraph; defaults in roles/workflow_designer/prompts.py (import via assistants.prompts).
RL Coach: config edits (deep merge) → TrainingConfig; defaults in roles/rl_coach/prompts.py (import via assistants.prompts).

Graph apply helper: ``gui.components.workflow.edit_workflows.runner.apply_edit_via_workflow`` (re-exported below).
Training apply helper: ``gui.components.workflow.edit_workflows.training_edit_runner.apply_training_config_edit`` (re-exported below).

Graph edit types and apply_graph_edit live in core.graph; use: from core.graph import GraphEdit, apply_graph_edit.
"""
from core.gym.training_edits import apply_config_edit, deep_merge
from assistants.prompts import RL_COACH_SYSTEM, WORKFLOW_DESIGNER_SYSTEM
from core.graph import apply_workflow_edits, graph_summary
from gui.components.workflow.edit_workflows import (
    apply_edit_via_workflow,
    apply_training_config_edit,
    training_config_summary,
)
from units.canonical.process_agent.action_blocks import parse_workflow_edits

__all__ = [
    "apply_config_edit",
    "apply_workflow_edits",
    "deep_merge",
    "graph_summary",
    "parse_workflow_edits",
    "apply_edit_via_workflow",
    "apply_training_config_edit",
    "training_config_summary",
    "RL_COACH_SYSTEM",
    "WORKFLOW_DESIGNER_SYSTEM",
]
