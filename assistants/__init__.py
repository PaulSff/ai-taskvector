"""
Assistants: apply structured edits → normalizer → canonical graph/config.
Workflow Designer: graph edits (add/remove/connect) → ProcessGraph; prompt in prompts.WORKFLOW_DESIGNER_SYSTEM.
RL Coach: config edits (deep merge) → TrainingConfig; prompt in prompts.RL_COACH_SYSTEM.
Text-to-reward: natural language → reward edit via Ollama → merge into TrainingConfig.

Graph edit types and apply_graph_edit live in core.graph; use: from core.graph import GraphEdit, apply_graph_edit.
"""
from core.gym.training_edits import apply_config_edit, deep_merge
from assistants.prompts import RL_COACH_SYSTEM, WORKFLOW_DESIGNER_SYSTEM
from assistants.process_assistant import (
    apply_workflow_edits,
    graph_summary,
    parse_workflow_edits,
    process_assistant_apply,
)
from assistants.training_assistant import training_assistant_apply, training_config_summary
from assistants.text_to_reward import text_to_reward, text_to_reward_apply

__all__ = [
    "apply_config_edit",
    "apply_workflow_edits",
    "deep_merge",
    "graph_summary",
    "parse_workflow_edits",
    "process_assistant_apply",
    "RL_COACH_SYSTEM",
    "training_assistant_apply",
    "training_config_summary",
    "text_to_reward",
    "text_to_reward_apply",
    "WORKFLOW_DESIGNER_SYSTEM",
]
