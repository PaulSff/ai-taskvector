"""
Build ``initial_inputs`` dicts for ``rl_coach_workflow.json`` (inject_* keys).

Kept under ``assistants/roles/rl_coach`` so headless code and tests do not depend on Flet.
"""
from __future__ import annotations

from typing import Any

from assistants.roles.workflow_designer.workflow_inputs import build_assistant_workflow_initial_inputs


def build_rl_coach_training_inject_updates(
    training_config: str,
    training_results: str,
    training_config_dict: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Inject ports for training summary, results snippet, and full config dict (ApplyTrainingConfigEdits)."""
    return {
        "inject_training_config": {"data": (training_config or "").strip()},
        "inject_training_results": {"data": (training_results or "").strip()},
        "inject_training_config_dict": {"data": training_config_dict or {}},
        "inject_empty_diff": {"data": ""},
    }


def build_rl_coach_assistant_aligned_initial_inputs(
    user_message: str,
    graph: Any,
    last_apply_result: dict[str, Any] | None,
    recent_changes: str | None,
    *,
    training_config: str,
    training_results: str,
    previous_turn: str,
    training_config_dict: dict[str, Any],
    follow_up_context: str = "",
    runtime: str = "external",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool = False,
    language_hint: str | None = None,
    session_language: str = "",
    analyst_mode: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Merge Workflow-Designer-style injects (graph, follow-up context, session language, …)
    with RL-specific training injects for ``rl_coach_workflow.json``.
    """
    base = build_assistant_workflow_initial_inputs(
        user_message,
        graph,
        last_apply_result,
        recent_changes,
        follow_up_context,
        runtime=runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        previous_turn=previous_turn,
        language_hint=language_hint,
        session_language=session_language,
        analyst_mode=analyst_mode,
    )
    base.update(
        build_rl_coach_training_inject_updates(
            training_config, training_results, training_config_dict
        )
    )
    return base


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
    out["inject_empty_diff"] = {"data": ""}
    return out
