from __future__ import annotations

from core.schemas.primitives import Data, WorkflowInputs
from core.schemas.process_graph import ProcessGraph


def build_self_correction_retry_inputs(
    failed_apply_result: Data,
    graph: ProcessGraph,
    recent_changes: str | None,
    runtime: str = "native",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool | None = None,
    previous_turn: str = "",
    language_hint: str | None = None,
    session_language: str = "",
    *,
    analyst_mode: bool = False,
) -> WorkflowInputs:
    # lazy imports to break cycle
    from agents.prompts import WORKFLOW_DESIGNER_RETRY_USER
    from agents.roles.workflow_designer.workflow_inputs import (
        build_agent_workflow_initial_inputs,
        default_wf_language_hint,
    )

    err_str = str(failed_apply_result.get("error", "Unknown"))[:500]
    if language_hint is None:
        language_hint = default_wf_language_hint(session_language)
    lang = (language_hint or "English (en)").strip() or "English (en)"
    retry_user_message = WORKFLOW_DESIGNER_RETRY_USER.format(
        error=err_str,
        language=lang,
        session_language=session_language,
    )

    # keep the existing behavior; this function used to import get_contribution_is_allowed
    from gui.components.settings import get_contribution_is_allowed

    _contrib = get_contribution_is_allowed() if contribution_is_allowed is None else contribution_is_allowed

    return build_agent_workflow_initial_inputs(
        retry_user_message,
        graph,
        failed_apply_result,
        recent_changes,
        follow_up_context="",
        runtime=runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=_contrib,
        previous_turn=(previous_turn or "").strip(),
        language_hint=lang,
        session_language=session_language,
        analyst_mode=analyst_mode,
    )
