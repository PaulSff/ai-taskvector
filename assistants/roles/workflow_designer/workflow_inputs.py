"""
Build ``initial_inputs`` dicts for ``assistant_workflow.json`` (inject_* keys).

Kept under ``assistants/roles/workflow_designer`` so headless code and tests do not depend on Flet.
"""
from __future__ import annotations

from typing import Any

from assistants.prompts import (
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

DEFAULT_WF_LANGUAGE = "English (en)"


def default_wf_language_hint(session_language: str) -> str:
    """Default language label for merge ``language_hint`` when nothing is pinned yet."""
    return (session_language or DEFAULT_WF_LANGUAGE).strip() or DEFAULT_WF_LANGUAGE


def _build_turn_state_string(last_apply_result: dict[str, Any] | None) -> str:
    """Build the turn state line for inject_turn_state (e.g. 'Turn state: Last action: none.')."""
    if last_apply_result is None:
        return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Last action: none."
    if last_apply_result.get("success") is False:
        err = last_apply_result.get("error") or "Unknown error"
        return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + f"Last action: failed (error: {err})."
    summary = last_apply_result.get("edits_summary") or ""
    if summary:
        return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + f"Last action: applied successfully ({summary})."
    return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Last action: applied successfully."


def _build_last_edit_block_string(
    last_apply_result: dict[str, Any] | None,
    self_correction_template: str = WORKFLOW_DESIGNER_SELF_CORRECTION,
    *,
    language: str = "English (en)",
) -> str:
    """Build the last-edit paragraph for inject_last_edit_block (failed/applied or empty)."""
    if last_apply_result is None:
        return ""
    if last_apply_result.get("success") is False:
        error_msg = last_apply_result.get("error") or "Unknown error"
        try:
            sc_text = self_correction_template.format(
                error=error_msg,
                language=language,
                session_language=language,
            )
        except KeyError:
            sc_text = self_correction_template.format(error=error_msg)
        return "Last edit failed. " + sc_text + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT
    summary = last_apply_result.get("edits_summary") or ""
    if summary:
        return "Last edit applied successfully. Applied: " + summary + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT
    return "Last edit applied successfully.\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT


def build_assistant_workflow_initial_inputs(
    user_message: str,
    graph: Any,
    last_apply_result: dict[str, Any] | None,
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
) -> dict[str, dict[str, Any]]:
    """
    Build initial_inputs for run_workflow(assistant_workflow.json).
    Graph can be dict or ProcessGraph (will be normalized to dict).
    recent_changes: optional diff text from previous run (e.g. get_recent_changes()).
    follow_up_context: optional injected context for follow-up runs (file content, RAG, web, browse, code blocks).
    runtime: "native" | "external" — used to set inject_add_environment_edit, inject_add_code_block_edit, inject_run_workflow, inject_ai_training_integration, inject_running_flow_line, inject_debugging_line, inject_coding_line (line or ""). Caller should derive from the graph via core.normalizer.runtime_detector.is_canonical_runtime(graph) → "native" if True else "external".
    coding_is_allowed: when true and runtime is native, inject_add_code_block_edit and inject_coding_line get the line; else "".
    contribution_is_allowed: when true together with native runtime and coding_is_allowed, inject_list_unit_edit and inject_list_environment_edit get the scaffold lines; else "".
    previous_turn: optional formatted last user+assistant turn (including any RAG/search context) so the model has one prior turn in context.
    language_hint: optional display string for prompts (e.g. \"German (de)\"); if None, uses default
        from pinned session_language (same rule as chat: English until merge_response.language pins).
    session_language: language pinned for the chat session and injected as {session_language}.
    analyst_mode: when True, omit graph-edit prompt lines and recent-change / last-edit blocks (analyst chat).
    """
    # Keep a handle to the live schema instance; model_dump() can drop or distort nested metadata
    # (e.g. todo_list.tasks) in edge cases, which breaks mark_completed in ApplyEdits (empty list).
    graph_live = graph
    if graph is not None and hasattr(graph, "model_dump"):
        graph = graph.model_dump(by_alias=True)
    if graph is None or not isinstance(graph, dict):
        graph = {"units": [], "connections": []}
    user_message = (user_message or "").strip() or "(No message provided.)"
    if language_hint is None:
        language_hint = default_wf_language_hint(session_language)
    lang = (language_hint or "English (en)").strip() or "English (en)"
    turn_state = _build_turn_state_string(last_apply_result)
    recent_changes_block = (
        (WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX + (recent_changes or "") + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT)
        if (recent_changes or "").strip()
        else ""
    )
    last_edit_block = _build_last_edit_block_string(last_apply_result, language=lang)
    out: dict[str, dict[str, Any]] = {
        "inject_user_message": {"data": user_message},
        "inject_graph": {"data": graph},
        "inject_turn_state": {"data": turn_state},
        "inject_recent_changes_block": {"data": recent_changes_block},
        "inject_last_edit_block": {"data": last_edit_block},
    }
    out["inject_follow_up_context"] = {"data": (follow_up_context or "").strip()}
    out["inject_previous_turn"] = {"data": (previous_turn or "").strip()}
    out["inject_session_language"] = {"data": str(session_language or "").strip()}
    # Conditional prompt lines: inject per key (runtime/coding_is_allowed in handler)
    r = (runtime or "native").strip()
    out["inject_add_environment_edit"] = {"data": WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE.strip() if r == "native" else ""}
    out["inject_add_code_block_edit"] = {"data": WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE.strip() if (r == "native" and coding_is_allowed) else ""}
    out["inject_run_workflow"] = {"data": WORKFLOW_DESIGNER_RUN_WORKFLOW_LINE.strip() if r == "native" else ""}
    out["inject_ai_training_integration"] = {"data": WORKFLOW_DESIGNER_AI_TRAINING_NATIVE.strip() if r == "native" else (WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL.strip() if r == "external" else "")}
    out["inject_running_flow_line"] = {"data": WORKFLOW_DESIGNER_RUNNING_FLOW_LINE.strip() if r == "native" else ""}
    out["inject_debugging_line"] = {"data": WORKFLOW_DESIGNER_DEBUGGING_LINE.strip() if r == "native" else ""}
    out["inject_coding_line"] = {"data": WORKFLOW_DESIGNER_CODING_LINE.strip() if (r == "native" and coding_is_allowed) else ""}
    _contrib = r == "native" and coding_is_allowed and contribution_is_allowed
    out["inject_list_unit_edit"] = {"data": WORKFLOW_DESIGNER_LIST_UNIT_LINE.strip() if _contrib else ""}
    out["inject_list_environment_edit"] = {"data": WORKFLOW_DESIGNER_LIST_ENVIRONMENT_LINE.strip() if _contrib else ""}
    # Ensure inject_graph carries the same todo_list as the canvas ProcessGraph (source of truth).
    inject_data = out["inject_graph"].get("data")
    if isinstance(inject_data, dict) and graph_live is not None:
        tl_live = getattr(graph_live, "todo_list", None)
        if tl_live is not None and hasattr(tl_live, "model_dump"):
            inject_data["todo_list"] = tl_live.model_dump(by_alias=True)
        elif tl_live is not None and isinstance(tl_live, dict):
            inject_data["todo_list"] = dict(tl_live)
    if analyst_mode:
        out["inject_recent_changes_block"] = {"data": ""}
        out["inject_last_edit_block"] = {"data": ""}
        out["inject_turn_state"] = {
            "data": WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Analyst: use tools and comments/todos only; do not edit graph structure.",
        }
        for k in (
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
            out[k] = {"data": ""}
    return out
