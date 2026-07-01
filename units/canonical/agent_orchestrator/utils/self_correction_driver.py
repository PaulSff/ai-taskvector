import asyncio
import inspect
from typing import Any, Callable

from units.canonical.agent_orchestrator.utils.proxies import (
    _SessionProxy,
)


async def _run_self_correction_retry_async(
    failed_apply_result: dict[str, Any],
    session: _SessionProxy,
    role_config: dict[str, Any],
    graph_ref: list[Any],
    last_apply_result_ref: list[Any],
    wf_language_hint: list[str],
    stream_cb: Callable[[str], None] | None,
    history: list[Any],
    recent_changes: str | None,
    coding_is_allowed: bool,
    contribution_is_allowed: bool,
    role_id: str,
) -> tuple[dict[str, Any], Any, str | None]:
    """
    Async wrapper for _run_self_correction_retry that runs blocking parts in threadpool.
    Returns (retry_response, retry_result_dict_or_None, retry_reply_or_None).
    """
    from agents.roles.workflow_designer.workflow_inputs import default_wf_language_hint
    from gui.chat.agent_workflow.helpers import (
        build_self_correction_retry_inputs,
        get_runtime_for_prompts,
        refresh_last_apply_result_after_canvas_apply,
    )
    from gui.chat.agent_workflow.run import run_agent_workflow
    from gui.chat.context.language_control import (
        maybe_pin_session_language_from_workflow_response,
    )
    from gui.chat.context.todo_list_manager import augment_graph_with_client_tasks
    from gui.chat.handlers.chat_turn_context import format_previous_turn
    from gui.chat.role_turns.turn_edits import canonicalize_add_comment_edits

    overrides = role_config["overrides"]
    agent_workflow_path = role_config["workflow_path"]

    _graph = graph_ref[0]
    _runtime = await get_runtime_for_prompts(_graph)
    _previous_turn = await format_previous_turn(history)

    retry_inputs = build_self_correction_retry_inputs(
        failed_apply_result,
        _graph,
        recent_changes,
        runtime=_runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        previous_turn=_previous_turn,
        language_hint=wf_language_hint[0],
        session_language=session.session_language,
    )

    try:
        retry_response = await run_agent_workflow(
            retry_inputs,
            overrides,
            None,
            stream_cb,
            workflow_path=agent_workflow_path,
        )
    except Exception:
        return {}, None, None

    maybe_pin_session_language_from_workflow_response(session, retry_response)
    wf_language_hint[0] = default_wf_language_hint(session.session_language)

    r_result = retry_response.get("result") or {}
    # canonicalize_add_comment_edits is sync; run in thread
    await asyncio.to_thread(
        lambda: canonicalize_add_comment_edits(
            r_result.get("edits"), agent_role_id=role_id
        )
    )
    r_kind = r_result.get("kind")
    retry_content: str | None = None

    if r_kind == "applied" and r_result.get("graph") is not None:
        graph_to_apply = r_result["graph"]
        if isinstance(graph_to_apply, dict):
            graph_to_apply, _retry_supp = augment_graph_with_client_tasks(
                graph_to_apply,
                r_result.get("edits") or [],
                coding_is_allowed=coding_is_allowed,
            )
            try:
                from gui.components.workflow_tab.workflows.core_workflows import (
                    validate_graph_to_apply_for_canvas,
                )

                vg, v_err = await validate_graph_to_apply_for_canvas(graph_to_apply)
                if not v_err and vg is not None:
                    graph_to_apply = vg
                else:
                    graph_to_apply = None
            except Exception:
                pass
                if graph_to_apply is not None:
                    graph_ref[0] = graph_to_apply
                    last_apply_result_ref[0] = (
                        refresh_last_apply_result_after_canvas_apply(
                            last_apply_result_ref[0],
                            graph_ref[0],
                            supplement_summary="",
                        )
                    )

        retry_raw = retry_response.get("reply") or ""
        retry_content = (
            retry_raw if isinstance(retry_raw, str) else str(retry_raw or "")
        ).strip() or None
    elif r_kind == "apply_failed":
        failed_apply = (
            r_result.get("last_apply_result") or r_result.get("apply_result") or {}
        )
        last_apply_result_ref[0] = (
            failed_apply
            if isinstance(failed_apply, dict) and not inspect.isawaitable(failed_apply)
            else {}
        )

    return retry_response, r_result, retry_content
