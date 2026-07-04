"""
Async agent turn runner: unpacks context dict and drives the full orchestration pipeline.

Called from AgentOrchestrator._agent_orchestrator_step (sync unit step function).
"""

from __future__ import annotations

import asyncio
import inspect
import time
import traceback
from typing import Any, Callable

from gui.chat.parser_follow_up.chain import (
    PostApplyFlags,
    run_parser_output_follow_up_chain_async,
    run_post_apply_follow_up_rounds_async,
)
from runtime.run import INLINE_STATUS_FOR_STREAMING
from runtime.stream_ui_signals import inline_status_stream_chunk
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
    _run_self_correction_retry_async,
)
from units.canonical.agent_orchestrator.utils.time import _now_ts

from .utils.batch_update_helpers import make_publish_in_progress

# ─── Main entry point ─────────────────────────────────────────────────────────


async def run_orchestrator_turn(
    context: dict[str, Any],
    *,
    stream_callback: Callable[[str], None] | None = None,
    batch_update_publisher=None,
    run_id: str | None,
) -> dict[str, Any]:
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

    # --- Safe defaults for the batch publisher ---

    result: dict[str, Any] = {}
    content: str = ""
    apply_meta: dict[str, Any] = {}
    response: dict[str, Any] = {}

    _publish_in_progress = make_publish_in_progress(
        batch_update_publisher=batch_update_publisher,
        run_id=run_id,  # passed through from agent_orchestrator
        get_role_id=lambda: role_id,
        get_agent_display=lambda: agent_display,
        get_turn_id=lambda: turn_id,
        get_messenger=lambda: messenger,
        get_follow_up_contexts=lambda: follow_up_contexts,
        get_graph_ref=lambda: _coerce_graph(graph_ref[0]),
        get_last_apply_result=lambda: last_apply_result_ref[0] or {},
        get_result=lambda: result,
        get_content=lambda: content,
        get_response=lambda: response,
        get_apply_meta=lambda: apply_meta,
        get_session_language=lambda: session.session_language,
        get_run_output=lambda: (response or {}).get("run_output") or {},
        get_source=lambda: "agent_response",
    )

    # --- Logging ---
    async def _checkpoint(name: str) -> None:
        # replace print with your logger if available
        print(f"[orchestrator] checkpoint: {name} ts={time.time():.3f}")

    async def _await_with_log(name: str, awaitable):
        t0 = time.time()
        try:
            await _checkpoint(f"enter:{name}")
            res = await awaitable
            print(f"[orchestrator] done:{name} dt={time.time() - t0:.3f}s")
            return res
        except Exception as exc:
            print(
                f"[orchestrator] FAIL:{name} dt={time.time() - t0:.3f}s exc={type(exc).__name__}: {exc}"
            )
            traceback.print_exc()
            raise

    # ── Inline status ──
    def _maybe_thinking_on() -> None:
        try:
            if callable(stream_callback):
                stream_callback(inline_status_stream_chunk(INLINE_STATUS_FOR_STREAMING))
        except Exception:
            pass

    def _maybe_thinking_off() -> None:
        try:
            if callable(stream_callback):
                stream_callback(inline_status_stream_chunk(None))
        except Exception:
            pass

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

    timeout_s = context.get("timeout_s")
    if timeout_s is None:
        timeout_s = context.get("orchestrator_timeout_s")
    # you can leave it unused if you want pure logging only

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
    follow_up_contexts: list[str] = []

    # ── Build initial workflow inputs ──
    initial_inputs = await _build_initial_inputs(
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
    try:
        # set the inline status "Thinking..."
        _maybe_thinking_on()

        if timeout_s is not None:
            response = await _await_with_log(
                "run_agent_workflow(timed)",
                asyncio.wait_for(
                    run_agent_workflow(
                        initial_inputs,
                        role_config["overrides"],
                        None,
                        stream_callback,
                        workflow_path=role_config["workflow_path"],
                    ),
                    timeout=timeout_s,
                ),
            )
        else:
            response = await _await_with_log(
                "run_agent_workflow",
                run_agent_workflow(
                    initial_inputs,
                    role_config["overrides"],
                    None,
                    stream_callback,
                    workflow_path=role_config["workflow_path"],
                ),
            )
    except WorkflowTimeoutError as ex:
        # ---stop inline status "Thinking" ---
        _maybe_thinking_off()
        timeout_s2 = getattr(ex, "timeout_s", 300)
        content = (
            f"(Request timed out after {timeout_s2:.0f}s. "
            "Try again or check that the LLM/service is responding.)"
        )
        result = {
            "kind": "parse_error",
            "content_for_display": content,
            "apply_result": {},
            "edits": [],
        }
        last_apply_result_ref[0] = {}
        await _checkpoint("after:WorkflowTimeoutError")
    except Exception as exc:
        # ---stop inline status "Thinking" ---
        _maybe_thinking_off()
        content = f"(Workflow error: {exc})"
        result = {
            "kind": "parse_error",
            "content_for_display": content,
            "apply_result": {},
            "edits": [],
        }
        last_apply_result_ref[0] = {}
        await _checkpoint("after:WorkflowException")
    else:
        # ---stop inline status "Thinking" ---
        _maybe_thinking_off()
        # ── Pin session language ──
        await _checkpoint("before:maybe_pin_session_language")
        maybe_pin_session_language_from_workflow_response(session, response)
        wf_language_hint[0] = default_wf_language_hint(session.session_language)
        await _checkpoint("after:maybe_pin_session_language")

        # ── Check delegation ──
        await _checkpoint("before:delegate_check")
        dr_out = response.get("delegate_request")
        if isinstance(dr_out, dict) and dr_out.get("ok") is True:
            dt = str(dr_out.get("delegate_to") or "").strip().lower()
            if dt and dt != role_id.lower():
                await _checkpoint("delegating:early_return")
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
        await _checkpoint("after:delegate_check")

        # Start inline "thinking..." once we've decided we are NOT delegating away.
        _maybe_thinking_on()

        # ── Follow-up chain (tool rounds) ──
        if asyncio.iscoroutine(response):
            response = await response
        if not isinstance(response, dict):
            raise TypeError(
                f"Expected workflow response dict, got {type(response).__name__}"
            )

        await _checkpoint("before:build_parser_follow_up_context")
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

        async def _parser_chain_runner_async(resp: dict[str, Any]) -> dict[str, Any]:
            await _checkpoint("parser_chain_runner:enter")
            chained = await run_parser_output_follow_up_chain_async(parser_ctx, resp)
            await _checkpoint("parser_chain_runner:done")
            return chained if chained is not None else resp

        response = await _await_with_log(
            "parser_follow_up_chain",
            _parser_chain_runner_async(response),
        )

        # ── Build content & result ──
        await _checkpoint("before:build_content_result")
        raw_reply = response.get("reply")
        if isinstance(raw_reply, dict) and "action" in raw_reply:
            raw_reply = raw_reply.get("action") or ""
        content = (
            raw_reply if isinstance(raw_reply, str) else str(raw_reply or "")
        ).strip() or "(No response from model.)"

        wf_result = response.get("result") or {}
        result = dict(wf_result)

        edits = result.get("edits") or []
        await _checkpoint("before:canonicalize_add_comment_edits")
        await canonicalize_add_comment_edits(edits, agent_role_id=role_id)

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
        ap = wf_result.get("last_apply_result")
        last_apply_result_ref[0] = (
            ap if isinstance(ap, dict) and not inspect.isawaitable(ap) else {}
        )
        await _checkpoint("after:build_content_result")
        # Publish teh batch_update over zmq
        _publish_in_progress(
            stage="turn:workflow_completed",
            kind=result.get("kind"),
        )

        # ── Handle applied ──
        await _checkpoint("before:handle_kind_branch")
        if result.get("kind") == "applied" and result.get("graph") is not None:
            await _checkpoint("branch:applied")

            applied_graph, _supplements, _v_err = await _await_with_log(
                "apply_and_augment_graph",
                _apply_and_augment_graph(
                    result["graph"],
                    result.get("edits") or [],
                    {"coding_is_allowed": coding_is_allowed},
                    graph_ref,
                    last_apply_result_ref,
                ),
            )

            if applied_graph is not None:
                content_holder = [content]
                await _checkpoint("before:build_post_apply_context")
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
                await _checkpoint("after:build_post_apply_context")

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

                async def _parser_chain_for_post(r: dict[str, Any]) -> dict[str, Any]:
                    return await _parser_chain_runner_async(r)

                await _checkpoint("before:run_post_apply_follow_up_rounds_async")
                await _await_with_log(
                    "post_apply_follow_up_rounds_async",
                    run_post_apply_follow_up_rounds_async(
                        post_ctx,
                        result=result,
                        content_holder=content_holder,
                        parser_chain_runner=_parser_chain_for_post,
                        flags=flags,
                    ),
                )
                await _checkpoint("after:run_post_apply_follow_up_rounds_async")
                # Publish batch_update over zmq
                _publish_in_progress(
                    stage="turn:post_apply_completed",
                    kind=result.get("kind"),
                )

                content = content_holder[0]

        # ── Handle apply_failed ──
        elif result.get("kind") == "apply_failed" and not role_config["analyst_mode"]:
            await _checkpoint("branch:apply_failed")
            failed_apply = (
                result.get("last_apply_result") or result.get("apply_result") or {}
            )
            last_apply_result_ref[0] = (
                failed_apply
                if isinstance(failed_apply, dict)
                and not inspect.isawaitable(failed_apply)
                else {}
            )

            await _checkpoint("before:self_correction_retry")
            (
                _retry_resp,
                retry_result,
                retry_content,
            ) = await _await_with_log(
                "self_correction_retry_async",
                _run_self_correction_retry_async(
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
                ),
            )
            await _checkpoint("after:self_correction_retry_async")
            # Publish update_butch over zmq
            _publish_in_progress(
                stage="turn:self_correction_retry_completed",
                kind=(retry_result or {}).get("kind")
                if "retry_result" in locals()
                else result.get("kind"),
            )

            if retry_result and retry_result.get("kind") == "applied" and retry_content:
                content = content + "\n\n" + retry_content

        await _checkpoint("after:handle_kind_branch")

        # ── Finalize session language (WD only) ──
        if role_id == WORKFLOW_DESIGNER_ROLE_ID:
            await _checkpoint("before:finalize_session_language")
            finalize_workflow_designer_turn_session_language(session, response)
            await _checkpoint("after:finalize_session_language")

    # ── Assemble final output ──
    await _checkpoint("before:assemble_final_output")

    display_content = str(result.get("content_for_display") or content)
    display_content = display_content + formulas_calc_display_appendix(response)
    apply_meta = apply_meta_with_formulas_calc_tool_status(
        response, result.get("apply_result", {})
    )
    # Publish batch_update over zmq
    _publish_in_progress(
        stage="turn:completed",
        kind=result.get("kind"),
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

    out = {
        "status": None,
        "token": {"type": "token", "token": display_content},
        "message": {"type": "final", "message": final_message},
        "role": {"role_id": role_id, "name": agent_display},
        "error": None,
    }

    await _checkpoint("after:assemble_final_output")
    return out
