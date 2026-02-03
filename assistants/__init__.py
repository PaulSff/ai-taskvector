"""
Assistants: apply structured edits → normalizer → canonical graph/config.
Workflow Designer: graph edits (add/remove/connect) → ProcessGraph; prompt in prompts.WORKFLOW_DESIGNER_SYSTEM.
RL Coach: config edits (deep merge) → TrainingConfig; prompt in prompts.RL_COACH_SYSTEM.
Text-to-reward: natural language → reward edit via Ollama → merge into TrainingConfig.
"""
from assistants.graph_edits import GraphEdit, GraphEditAction, GraphEditUnit, apply_graph_edit
from assistants.config_edits import apply_config_edit, deep_merge
from assistants.prompts import RL_COACH_SYSTEM, WORKFLOW_DESIGNER_SYSTEM
from assistants.process_assistant import process_assistant_apply
from assistants.training_assistant import training_assistant_apply
from assistants.text_to_reward import text_to_reward, text_to_reward_apply

__all__ = [
    "GraphEdit",
    "GraphEditAction",
    "GraphEditUnit",
    "apply_graph_edit",
    "apply_config_edit",
    "deep_merge",
    "process_assistant_apply",
    "RL_COACH_SYSTEM",
    "training_assistant_apply",
    "text_to_reward",
    "text_to_reward_apply",
    "WORKFLOW_DESIGNER_SYSTEM",
]
