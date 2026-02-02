"""
Assistants: apply structured edits → normalizer → canonical graph/config.
Process Assistant: graph edits (add/remove/connect) → ProcessGraph.
Training Assistant: config edits (deep merge) → TrainingConfig.
Text-to-reward: natural language → reward edit via Ollama → merge into TrainingConfig.
"""
from assistants.graph_edits import GraphEdit, GraphEditAction, GraphEditUnit, apply_graph_edit
from assistants.config_edits import apply_config_edit, deep_merge
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
    "training_assistant_apply",
    "text_to_reward",
    "text_to_reward_apply",
]
