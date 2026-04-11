"""
Build ``initial_inputs`` dicts for ``rl_coach_workflow.json`` (inject_* keys).

Kept under ``assistants/roles/rl_coach`` so headless code and tests do not depend on Flet.
"""
from __future__ import annotations

from typing import Any


def build_rl_coach_initial_inputs(
    user_message: str,
    training_config: str = "",
    training_results: str = "",
    previous_turn: str = "",
    training_config_dict: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Build initial_inputs for run_workflow(rl_coach_workflow.json).
    Same pattern as Workflow Designer: separate injects for user_message (string, also drives RAG),
    training_config (summary string for prompt), training_results, previous_turn, and
    inject_training_config_dict (full config dict for ApplyTrainingConfigEdits). RAG context
    is produced inside the workflow (inject_user_message → RagSearch → Filter → FormatRagPrompt → Aggregate).
    """
    user_message = (user_message or "").strip() or "(No message provided.)"
    out: dict[str, dict[str, Any]] = {
        "inject_user_message": {"data": user_message},
        "inject_training_config": {"data": (training_config or "").strip()},
        "inject_training_results": {"data": (training_results or "").strip()},
        "inject_previous_turn": {"data": (previous_turn or "").strip()},
    }
    if training_config_dict is not None:
        out["inject_training_config_dict"] = {"data": training_config_dict}
    return out
