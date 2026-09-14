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
from core.schemas.graph_edit_api import (
    ApplyWorkflowEditsResult,
)
from core.schemas.primitives import WorkflowInputs

from .wf_inputs_schema import WorkflowDesignerWorkflowInputs

DEFAULT_WF_LANGUAGE = "English (en)"


def default_wf_language_hint(session_language: str) -> str:
    """Default language label for merge ``language_hint`` when nothing is pinned yet."""
    return (session_language or DEFAULT_WF_LANGUAGE).strip() or DEFAULT_WF_LANGUAGE


def _build_turn_state_string(
    last_apply_result: ApplyWorkflowEditsResult | None,
) -> str:
    """Build the turn state line for inject_turn_state."""
    prefix = WORKFLOW_DESIGNER_TURN_STATE_PREFIX

    if last_apply_result is None:
        return prefix + "Last action: none."

    if not last_apply_result.success:
        error = last_apply_result.error or "Unknown error"
        return prefix + f"Last action: failed (error: {error})."

    summary = (last_apply_result.edits_summary or "").strip()
    if summary:
        return prefix + f"Last action: applied successfully ({summary})."

    return prefix + "Last action: applied successfully."



def _build_last_edit_block_string(
    last_apply_result: ApplyWorkflowEditsResult | None,
    self_correction_template: str = WORKFLOW_DESIGNER_SELF_CORRECTION,
    *,
    language: str = "English (en)",
) -> str:
    """Build the last-edit paragraph for inject_last_edit_block."""
    if last_apply_result is None:
        return ""

    if not last_apply_result.success:
        error_msg = last_apply_result.error or "Unknown error"

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

    summary = (last_apply_result.edits_summary or "").strip()

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
    last_apply_result: ApplyWorkflowEditsResult | None,
    recent_changes: str | None,
    follow_up_context: str = "",
    runtime: str = "native",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool = False,
    previous_turn: str = "",
    language_hint: str | None = None,
    session_language: str = "",
    *,
    light_graph_mode: bool = False,
) -> WorkflowInputs:
    user_message = (user_message or "").strip() or "(No message provided.)"

    if language_hint is None:
        language_hint = default_wf_language_hint(session_language)

    lang = (language_hint or "English (en)").strip() or "English (en)"
    runtime_value = (runtime or "native").strip()

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

    is_native = runtime_value == "native"
    can_add_code = is_native and coding_is_allowed
    can_contribute = can_add_code and contribution_is_allowed

    inputs = WorkflowDesignerWorkflowInputs(
        inject_user_message=user_message,
        inject_graph=graph,
        inject_turn_state=turn_state,
        inject_recent_changes_block=recent_changes_block,
        inject_last_edit_block=last_edit_block,
        inject_follow_up_context=(follow_up_context or "").strip(),
        inject_previous_turn=(previous_turn or "").strip(),
        inject_session_language=(session_language or "").strip(),
        inject_add_environment_edit=(
            WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE.strip()
            if is_native
            else ""
        ),
        inject_add_code_block_edit=(
            WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE.strip()
            if can_add_code
            else ""
        ),
        inject_run_workflow=(
            WORKFLOW_DESIGNER_RUN_WORKFLOW_LINE.strip()
            if is_native
            else ""
        ),
        inject_ai_training_integration=(
            WORKFLOW_DESIGNER_AI_TRAINING_NATIVE.strip()
            if is_native
            else (
                WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL.strip()
                if runtime_value == "external"
                else ""
            )
        ),
        inject_running_flow_line=(
            WORKFLOW_DESIGNER_RUNNING_FLOW_LINE.strip()
            if is_native
            else ""
        ),
        inject_debugging_line=(
            WORKFLOW_DESIGNER_DEBUGGING_LINE.strip()
            if is_native
            else ""
        ),
        inject_coding_line=(
            WORKFLOW_DESIGNER_CODING_LINE.strip()
            if can_add_code
            else ""
        ),
        inject_list_unit_edit=(
            WORKFLOW_DESIGNER_LIST_UNIT_LINE.strip()
            if can_contribute
            else ""
        ),
        inject_list_environment_edit=(
            WORKFLOW_DESIGNER_LIST_ENVIRONMENT_LINE.strip()
            if can_contribute
            else ""
        ),
    )

    if light_graph_mode:
        for field_name in (
            "inject_recent_changes_block",
            "inject_last_edit_block",
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
            setattr(inputs, field_name, "")

        inputs.inject_turn_state = (
            WORKFLOW_DESIGNER_TURN_STATE_PREFIX
            + "Analyst: use tools and comments/todos only; "
            + "do not edit graph structure."
        )

    return inputs.to_workflow_inputs()
