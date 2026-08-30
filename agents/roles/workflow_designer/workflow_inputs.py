"""
Build ``initial_inputs`` dicts for ``workflow_designer_workflow.json`` (inject_* keys).

Kept under ``agents/roles/workflow_designer`` so headless code and tests do not depend on Flet.
"""

from __future__ import annotations

from agents.prompts import (
    WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE,
    WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE,
    WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL,
    WORKFLOW_DESIGNER_AI_TRAINING_NATIVE,
    WORKFLOW_DESIGNER_CODING_LINE,
    WORKFLOW_DESIGNER_DEBUGGING_LINE,
    WORKFLOW_DESIGNER_DO_NOT_REPEAT,
    WORKFLOW_DESIGNER_LIST_ENVIRONMENT_LINE,
    WORKFLOW_DESIGNER_LIST_UNIT_LINE,
    WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX,
    WORKFLOW_DESIGNER_RUN_WORKFLOW_LINE,
    WORKFLOW_DESIGNER_RUNNING_FLOW_LINE,
    WORKFLOW_DESIGNER_SELF_CORRECTION,
    WORKFLOW_DESIGNER_TURN_STATE_PREFIX,
)
from core.schemas import ProcessGraph

DEFAULT_WF_LANGUAGE = "English (en)"


def default_wf_language_hint(session_language: str) -> str:
    """Default language label for merge ``language_hint`` when nothing is pinned yet."""
    return (session_language or DEFAULT_WF_LANGUAGE).strip() or DEFAULT_WF_LANGUAGE


def _build_turn_state_string(last_apply_result: dict[str, object] | None) -> str:
    """Build the turn state line for inject_turn_state (e.g. 'Turn state: Last action: none.')."""
    if last_apply_result is None:
        return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Last action: none."
    if last_apply_result.get("success") is False:
        err = last_apply_result.get("error") or "Unknown error"
        return (
            WORKFLOW_DESIGNER_TURN_STATE_PREFIX + f"Last action: failed (error: {err})."
        )
    summary = last_apply_result.get("edits_summary") or ""
    if summary:
        return (
            WORKFLOW_DESIGNER_TURN_STATE_PREFIX
            + f"Last action: applied successfully ({summary})."
        )
    return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Last action: applied successfully."


def _build_last_edit_block_string(
    last_apply_result: dict[str, object] | None,
    self_correction_template: str = WORKFLOW_DESIGNER_SELF_CORRECTION,
    *,
    language: str = "English (en)",
) -> str:
    """Build the last-edit paragraph for inject_last_edit_block."""
    if last_apply_result is None:
        return ""

    if last_apply_result.get("success") is False:
        raw_error = last_apply_result.get("error")
        error_msg = raw_error if isinstance(raw_error, str) else "Unknown error"

        try:
            sc_text = self_correction_template.format(
                error=error_msg,
                language=language,
                session_language=language,
            )
        except KeyError:
            sc_text = self_correction_template.format(error=error_msg)

        return (
            "Last edit failed. "
            + sc_text
            + "\n"
            + WORKFLOW_DESIGNER_DO_NOT_REPEAT
        )

    raw_summary = last_apply_result.get("edits_summary")
    summary = raw_summary if isinstance(raw_summary, str) else ""

    if summary:
        return (
            "Last edit applied successfully. Applied: "
            + summary
            + "\n"
            + WORKFLOW_DESIGNER_DO_NOT_REPEAT
        )

    return (
        "Last edit applied successfully.\n"
        + WORKFLOW_DESIGNER_DO_NOT_REPEAT
    )


def build_agent_workflow_initial_inputs(
    user_message: str,
    graph: ProcessGraph,
    last_apply_result: dict[str, object] | None,
    recent_changes: str | None,
    follow_up_context: str = "",
    runtime: str = "native",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool = False,
    previous_turn: str = "",
    language_hint: str | None = None,
    session_language: str = "",
    *,
    analyst_mode: bool = False,
) -> dict[str, dict[str, object]]:
    """
    Build initial_inputs for run_workflow(workflow_designer_workflow.json).

    The graph must be supplied as a ProcessGraph. It is serialized only for
    injection into the workflow while preserving live todo-list data.
    """
    graph_live = graph

    graph_data = graph.model_dump(by_alias=True)

    user_message = (user_message or "").strip() or "(No message provided.)"

    if language_hint is None:
        language_hint = default_wf_language_hint(session_language)

    lang = (language_hint or "English (en)").strip() or "English (en)"
    turn_state = _build_turn_state_string(last_apply_result)

    recent_changes_block = (
        WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX
        + (recent_changes or "")
        + "\n"
        + WORKFLOW_DESIGNER_DO_NOT_REPEAT
        if (recent_changes or "").strip()
        else ""
    )

    last_edit_block = _build_last_edit_block_string(
        last_apply_result,
        language=lang,
    )

    out: dict[str, dict[str, object]] = {
        "inject_user_message": {"data": user_message},
        "inject_graph": {"data": graph_data},
        "inject_turn_state": {"data": turn_state},
        "inject_recent_changes_block": {"data": recent_changes_block},
        "inject_last_edit_block": {"data": last_edit_block},
        "inject_follow_up_context": {
            "data": (follow_up_context or "").strip()
        },
        "inject_previous_turn": {
            "data": (previous_turn or "").strip()
        },
        "inject_session_language": {
            "data": str(session_language or "").strip()
        },
    }

    r = (runtime or "native").strip()

    out["inject_add_environment_edit"] = {
        "data": (
            WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE.strip()
            if r == "native"
            else ""
        )
    }
    out["inject_add_code_block_edit"] = {
        "data": (
            WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE.strip()
            if r == "native" and coding_is_allowed
            else ""
        )
    }
    out["inject_run_workflow"] = {
        "data": (
            WORKFLOW_DESIGNER_RUN_WORKFLOW_LINE.strip()
            if r == "native"
            else ""
        )
    }
    out["inject_ai_training_integration"] = {
        "data": (
            WORKFLOW_DESIGNER_AI_TRAINING_NATIVE.strip()
            if r == "native"
            else (
                WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL.strip()
                if r == "external"
                else ""
            )
        )
    }
    out["inject_running_flow_line"] = {
        "data": (
            WORKFLOW_DESIGNER_RUNNING_FLOW_LINE.strip()
            if r == "native"
            else ""
        )
    }
    out["inject_debugging_line"] = {
        "data": (
            WORKFLOW_DESIGNER_DEBUGGING_LINE.strip()
            if r == "native"
            else ""
        )
    }
    out["inject_coding_line"] = {
        "data": (
            WORKFLOW_DESIGNER_CODING_LINE.strip()
            if r == "native" and coding_is_allowed
            else ""
        )
    }

    _contrib = (
        r == "native"
        and coding_is_allowed
        and contribution_is_allowed
    )

    out["inject_list_unit_edit"] = {
        "data": WORKFLOW_DESIGNER_LIST_UNIT_LINE.strip()
        if _contrib
        else ""
    }
    out["inject_list_environment_edit"] = {
        "data": WORKFLOW_DESIGNER_LIST_ENVIRONMENT_LINE.strip()
        if _contrib
        else ""
    }

    # Preserve todo_lists from the live ProcessGraph.
    tls_live = graph_live.todo_lists

    graph_data["todo_lists"] = [
        todo_list.model_dump(by_alias=True)
        for todo_list in tls_live
    ]

    if analyst_mode:
        out["inject_recent_changes_block"] = {"data": ""}
        out["inject_last_edit_block"] = {"data": ""}
        out["inject_turn_state"] = {
            "data": (
                WORKFLOW_DESIGNER_TURN_STATE_PREFIX
                + "Analyst: use tools and comments/todos only; "
                + "do not edit graph structure."
            )
        }

        for key in (
            "inject_add_environment_edit",
            "inject_add_code_block_edit",
            "inject_run_workflow",
            "inject_ai_training_integration",
            "inject_running_flow_line",
            "inject_debugging_line",
            "inject_coding_line",
            "inject_list_unit_edit",
            "inject_list_environment_edit",
        ):
            out[key] = {"data": ""}

    return out
