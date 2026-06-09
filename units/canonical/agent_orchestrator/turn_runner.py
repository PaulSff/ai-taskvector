"""
Sync agent turn runner: unpacks context dict and drives the full orchestration pipeline.

Called from AgentOrchestrator._agent_orchestrator_step (sync unit step function).
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from gui.chat.parser_follow_up.chain import (
    PostApplyFlags,
    run_parser_output_follow_up_chain,
    run_post_apply_follow_up_rounds,
)
from units.canonical.agent_orchestrator.utils.follow_up_context_builder import (
    _build_parser_follow_up_context,
)
from units.canonical.agent_orchestrator.utils.graph_augmenter import (
    _apply_and_augment_graph,
)
from units.canonical.agent_orchestrator.utils.graph_converter import _coerce_graph
from units.canonical.agent_orchestrator.utils.ids import _new_id
from units.canonical.agent_orchestrator.utils.inputs_builder import (
    _build_initial_inputs,
)
from units.canonical.agent_orchestrator.utils.post_apply_context_builder import (
    _build_post_apply_context,
)
from units.canonical.agent_orchestrator.utils.proxies import (
    _SessionProxy,
)
from units.canonical.agent_orchestrator.utils.role_config import _get_role_config
from units.canonical.agent_orchestrator.utils.self_correction_driver import (
    _run_self_correction_retry,
)
from units.canonical.agent_orchestrator.utils.time import _now_ts

# ─── Main entry point ─────────────────────────────────────────────────────────


def run_orchestrator_turn(
    context: dict[str, Any],
    *,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run one complete agent turn and return structured output port values.

    Drives: initial workflow → follow-up chain → apply/validate → post-apply rounds.

    Args:
        context: See AgentOrchestrator module docstring for accepted keys.
        stream_callback: Called for each LLM token chunk (same as all streaming units).

    Returns:
        Dict with keys: status, token, message, role, error.
    """
    from agents.roles.registry import (
        WORKFLOW_DESIGNER_ROLE_ID,
        get_role,
    )
    from agents.roles.workflow_designer.workflow_inputs import default_wf_language_hint
    from gui.chat.agent_workflow.run import run_agent_workflow
    from gui.chat.context.language_control import (
        finalize_workflow_designer_turn_session_language,
        maybe_pin_session_language_from_workflow_response,
    )
    from gui.chat.handlers.chat_turn_context import normalize_user_message_for_workflow
    from gui.chat.role_turns.turn_edits import canonicalize_add_comment_edits
    from gui.utils.workflow_output_normalizer import (
        apply_meta_with_formulas_calc_tool_status,
        formulas_calc_display_appendix,
    )
    from runtime.run import WorkflowTimeoutError

    # ── Unpack context ──

    user_message = normalize_user_message_for_workflow(
        context.get("user_message") or ""
    )
    messenger = str(context.get("messenger") or "")
    role_id = (
        str(
            context.get("role_id")
            or context.get("role_hint")
            or WORKFLOW_DESIGNER_ROLE_ID
        ).strip()
        or WORKFLOW_DESIGNER_ROLE_ID
    )

    history: list[Any] = list(context.get("history") or [])
    session_language = str(context.get("session_language") or "")
    last_apply_result: dict[str, Any] | None = context.get("last_apply_result")
    graph: Any = context.get("graph")
    recent_changes: str | None = context.get("recent_changes")
    provider = str(context.get("provider") or "ollama")
    cfg = dict(context.get("cfg") or {})
    mydata_dir = str(context.get("mydata_dir") or ".")
    coding_is_allowed = bool(context.get("coding_is_allowed", True))
    contribution_is_allowed = bool(context.get("contribution_is_allowed", False))

    # ── Mutable references ──

    graph_ref: list[Any] = [graph]
    last_apply_result_ref: list[Any] = [last_apply_result]
    wf_language_hint: list[str] = [default_wf_language_hint(session_language)]
    session = _SessionProxy(session_language=session_language, history=history)

    # ── Role resolution ──

    try:
        role = get_role(role_id)
    except Exception:
        role_id = WORKFLOW_DESIGNER_ROLE_ID
        role = get_role(role_id)
    agent_display = role.role_name or role_id

    # ── Role config ──

    try:
        role_config = _get_role_config(
            role_id,
            {
                "provider": provider,
                "cfg": cfg,
                "mydata_dir": mydata_dir,
                "coding_is_allowed": coding_is_allowed,
                "contribution_is_allowed": contribution_is_allowed,
            },
        )
    except Exception as exc:
        return {
            "status": None,
            "token": None,
            "message": None,
            "role": None,
            "error": {"type": "error", "error": f"Role config failed: {exc}"},
        }

    # ── graph_summary override ──
    # Adds dynamic params (coding_is_allowed + current graph) that depend on the
    # turn context and cannot be baked into the static role config.
    try:
        from gui.chat.context.todo_list_manager import get_summary_params

        graph_dict_for_summary = _coerce_graph(graph)
        if role_config["analyst_mode"]:
            role_config["overrides"]["graph_summary"] = {
                "include_code_block_source": False,
                "include_structure": False,
            }
        else:
            role_config["overrides"]["graph_summary"] = get_summary_params(
                coding_is_allowed, graph_dict_for_summary
            )
    except Exception:
        pass

    turn_id = _new_id()
    # messages: list[dict[str, Any]] = []
    follow_up_contexts: list[str] = []

    # ── Build initial workflow inputs ──

    initial_inputs = _build_initial_inputs(
        user_message,
        graph,
        last_apply_result,
        recent_changes,
        session_language,
        history,
        wf_language_hint[0],
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        analyst_mode=role_config["analyst_mode"],
    )

    # ── Run main workflow ──

    response: dict[str, Any] = {}
    content = ""
    result: dict[str, Any] = {}

    try:
        response = run_agent_workflow(
            initial_inputs,
            role_config["overrides"],
            None,  # execution_timeout_s → DEFAULT_EXECUTION_TIMEOUT_S
            stream_callback=stream_callback,
            workflow_path=role_config["workflow_path"],
        )
    except WorkflowTimeoutError as ex:
        timeout_s = getattr(ex, "timeout_s", 300)
        content = (
            f"(Request timed out after {timeout_s:.0f}s. "
            "Try again or check that the LLM/service is responding.)"
        )
        result = {
            "kind": "parse_error",
            "content_for_display": content,
            "apply_result": {},
            "edits": [],
        }
        last_apply_result_ref[0] = None
    except Exception as exc:
        content = f"(Workflow error: {exc})"
        result = {
            "kind": "parse_error",
            "content_for_display": content,
            "apply_result": {},
            "edits": [],
        }
        last_apply_result_ref[0] = None
    else:
        # ── Pin session language ──

        maybe_pin_session_language_from_workflow_response(session, response)
        wf_language_hint[0] = default_wf_language_hint(session.session_language)

        # ── Check delegation ──

        dr_out = response.get("delegate_request")
        if isinstance(dr_out, dict) and dr_out.get("ok") is True:
            dt = str(dr_out.get("delegate_to") or "").strip().lower()
            if dt and dt != role_id.lower():
                return {
                    "status": None,
                    "token": None,
                    "message": {
                        "type": "delegate",
                        "delegate_to": dt,
                        "original_role": role_id,
                    },
                    "role": {"role_id": dt, "name": dt},
                    "error": None,
                }

        # ── Follow-up chain (tool rounds) ──

        parser_ctx = _build_parser_follow_up_context(
            session=session,
            role_id=role_id,
            role_config=role_config,
            history=history,
            turn_id=turn_id,
            agent_display=agent_display,
            follow_up_contexts=follow_up_contexts,
            stream_cb=stream_callback,
            graph_ref=graph_ref,
            last_apply_result_ref=last_apply_result_ref,
            wf_language_hint=wf_language_hint,
            recent_changes=recent_changes,
        )

        def _parser_chain_runner(resp: dict[str, Any]) -> dict[str, Any]:
            chained = run_parser_output_follow_up_chain(parser_ctx, resp)
            return chained if chained is not None else resp

        response = _parser_chain_runner(response)

        # ── Build content & result ──

        raw_reply = response.get("reply")
        if isinstance(raw_reply, dict) and "action" in raw_reply:
            raw_reply = raw_reply.get("action") or ""
        content = (
            raw_reply if isinstance(raw_reply, str) else str(raw_reply or "")
        ).strip() or "(No response from model.)"

        wf_result = response.get("result") or {}
        result = dict(wf_result)
        # canonicalize_add_comment_edits(result.get("edits"), agent_role_id=role_id)
        edits = result.get("edits") or []
        canonicalize_add_comment_edits(edits, agent_role_id=role_id)
        result["edits"] = edits
        result["apply_result"] = (
            response.get("status") or wf_result.get("last_apply_result") or {}
        )
        ar0 = result.get("apply_result") or {}
        if (
            result.get("kind") != "apply_failed"
            and isinstance(ar0, dict)
            and ar0.get("attempted") is True
            and ar0.get("success") is False
        ):
            result["kind"] = "apply_failed"

        result["content_for_display"] = content
        last_apply_result_ref[0] = wf_result.get("last_apply_result")

        # ── Handle applied ──
        if result.get("kind") == "applied" and result.get("graph") is not None:
            # Always apply/augment the graph and run post-apply follow-ups for all roles
            applied_graph, _supplements, _v_err = _apply_and_augment_graph(
                result["graph"],
                result.get("edits") or [],
                {"coding_is_allowed": coding_is_allowed},
                graph_ref,
                last_apply_result_ref,
            )

            if applied_graph is not None:
                content_holder = [content]

                post_ctx = _build_post_apply_context(
                    session=session,
                    role_id=role_id,
                    role_config=role_config,
                    turn_id=turn_id,
                    graph_ref=graph_ref,
                    last_apply_result_ref=last_apply_result_ref,
                    wf_language_hint=wf_language_hint,
                    recent_changes=recent_changes,
                )

                flags = PostApplyFlags(
                    had_import_workflow=any(
                        isinstance(e, dict) and e.get("action") == "import_workflow"
                        for e in (result.get("edits") or [])
                    ),
                    had_todo=any(
                        isinstance(e, dict)
                        and e.get("action")
                        in {
                            "add_todo_list",
                            "remove_todo_list",
                            "add_task",
                            "remove_task",
                            "mark_completed",
                        }
                        for e in (result.get("edits") or [])
                    ),
                    had_add_comment=any(
                        isinstance(e, dict) and e.get("action") == "add_comment"
                        for e in (result.get("edits") or [])
                    ),
                )

                run_post_apply_follow_up_rounds(
                    post_ctx,
                    result=result,
                    content_holder=content_holder,
                    parser_chain_runner=lambda r: asyncio.sleep(
                        0, result=_parser_chain_runner(r)
                    ),
                    flags=flags,
                )

                content = content_holder[0]

        # ── Handle apply_failed ──

        elif result.get("kind") == "apply_failed" and not role_config["analyst_mode"]:
            failed_apply = (
                result.get("last_apply_result") or result.get("apply_result") or {}
            )
            last_apply_result_ref[0] = failed_apply
            _retry_resp, retry_result, retry_content = _run_self_correction_retry(
                failed_apply,
                session,
                role_config,
                graph_ref,
                last_apply_result_ref,
                wf_language_hint,
                stream_callback,
                history,
                recent_changes,
                coding_is_allowed,
                contribution_is_allowed,
                role_id,
            )
            if retry_result and retry_result.get("kind") == "applied" and retry_content:
                content = content + "\n\n" + retry_content

        # ── Finalize session language (WD only) ──

        if role_id == WORKFLOW_DESIGNER_ROLE_ID:
            finalize_workflow_designer_turn_session_language(session, response)

    # ── Assemble final output ──

    display_content = str(result.get("content_for_display") or content)
    display_content = display_content + formulas_calc_display_appendix(response)
    apply_meta = apply_meta_with_formulas_calc_tool_status(
        response, result.get("apply_result", {})
    )

    final_message: dict[str, Any] = {
        "id": _new_id(),
        "ts": _now_ts(),
        "role": "agent",
        "content": display_content,
        "agent": agent_display,
        "turn_id": turn_id,
        "source": "agent_response",
        "workflow_response": {
            "reply": display_content,
            "result_kind": result.get("kind"),
        },
        "parsed_edits": result.get("edits", []),
        "apply": apply_meta,
        "graph": _coerce_graph(graph_ref[0]),
        "run_output": response.get("run_output") or {},
        "follow_up_contexts": follow_up_contexts,
        "last_apply_result": last_apply_result_ref[0],
        "session_language": session.session_language,
        "messenger": messenger,
        "llm_user_message": response.get("llm_user_message"),
        "llm_system_prompt": response.get("llm_system_prompt"),
    }

    return {
        "status": None,
        "token": {"type": "token", "token": display_content},
        "message": {"type": "final", "message": final_message},
        "role": {"role_id": role_id, "name": agent_display},
        "error": None,
    }
