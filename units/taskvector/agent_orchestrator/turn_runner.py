"""
Async agent turn runner: unpacks context dict and drives the full orchestration pipeline.

Called from AgentOrchestrator._agent_orchestrator_step (sync unit step function).
"""

from __future__ import annotations

import asyncio
import time
import traceback
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from agents.chat.agent_workflow import AgentWorkflowResponse
from agents.chat.context.follow_up_context import (
    PostEditFlags,
)
from agents.chat.context.todo_list_manager.helpers import graph_has_any_open_tasks
from agents.chat.parser_follow_up.chain import (
    run_execution_follow_up_chain_async,
    run_post_execution_follow_up_chain_async,
)
from agents.chat.session.state import AgentChatHistory
from core.normalizer.normalizer import graph_to_json_object
from core.normalizer.shared import as_workflow_inputs, to_json_value
from core.schemas import ProcessGraph
from core.schemas.graph_edit_api import (
    COMMENT_ACTIONS,
    IMPORT_WORKFLOW_ACTION,
    TODO_ACTIONS,
    AgentApplyWorkflowEditsResult,
)
from core.schemas.primitives import Data, WorkflowInputs
from runtime.executor import GraphStreamCallback
from runtime.run import INLINE_STATUS_FOR_STREAMING
from runtime.stream_ui_signals import inline_status_stream_chunk
from units.taskvector.agent_orchestrator.utils.follow_up_context_builder import (
    build_parser_follow_up_context,
)
from units.taskvector.agent_orchestrator.utils.graph_augmenter import (
    apply_and_augment_graph,
)
from units.taskvector.agent_orchestrator.utils.graph_converter import coerce_graph
from units.taskvector.agent_orchestrator.utils.ids import new_id
from units.taskvector.agent_orchestrator.utils.inputs_builder import (
    build_initial_inputs,
)
from units.taskvector.agent_orchestrator.utils.post_apply_context_builder import (
    build_post_apply_context,
)
from units.taskvector.agent_orchestrator.utils.proxies import (
    SessionProxy,
)
from units.taskvector.agent_orchestrator.utils.self_correction_driver import (
    run_self_correction_retry_async,
)
from units.taskvector.agent_orchestrator.utils.time import now_ts

from .utils.batch_update_helpers import (
    ProgressResponse,
    ProgressResult,
    make_publish_in_progress,
)
from .utils.batch_update_publisher import BatchUpdatePublisher
from .utils.graph_hasher import graph_md5
from .utils.merge_final_graph import merge_latest_graph_for_final_output

# ─── Main entry point ─────────────────────────────────────────────────────────


async def run_orchestrator_turn(
    context: Data,
    *,
    stream_callback: GraphStreamCallback | None = None,
    batch_update_publisher: BatchUpdatePublisher | None = None,
    run_id: str | None,
) -> Data:
    from agents.chat.agent_workflow.run_agent_workflow import run_agent_workflow
    from agents.chat.context.language_control import (
        finalize_workflow_designer_turn_session_language,
        maybe_pin_session_language_from_workflow_response,
    )
    from agents.chat.handlers.chat_turn_context import (
        normalize_user_message_for_workflow,
    )
    from agents.chat.role_turns.turn_edits import set_commenter_for_new_comments
    from agents.chat.utils.workflow_output_normalizer import (
        apply_meta_with_formulas_calc_tool_status,
        formulas_calc_display_appendix,
    )
    from agents.roles.registry import (
        WORKFLOW_DESIGNER_ROLE_ID,
        get_role,
    )
    from agents.roles.workflow_designer.workflow_inputs import default_wf_language_hint
    from runtime.run import WorkflowTimeoutError

    # --- Safe defaults for the batch publisher ---
    response = ProgressResponse()
    result: ProgressResult = {}
    content: str = ""
    apply_meta: Data = {}

    # Capture fallback graph so we can still assemble output on errors
    raw_graph = context.get("graph")

    if raw_graph is None:
        raise ValueError("Missing process graph")

    graph: ProcessGraph = ProcessGraph.model_validate(raw_graph)

    fallback_graph: ProcessGraph | None = graph

    followup_error: Data | None = None

    def _get_progress_response() -> ProgressResponse | None:
        if isinstance(response, dict):
            return cast(ProgressResponse, response)
        return None

    def _get_run_output() -> Data:
        if not isinstance(response, Mapping):
            return {}

        run_output = response.get("run_output")
        return run_output if isinstance(run_output, dict) else {}


    _publish_in_progress = make_publish_in_progress(
        batch_update_publisher=batch_update_publisher,
        run_id=run_id,  # passed through from agent_orchestrator
        get_role_id=lambda: role_id,
        get_agent_display=lambda: agent_display,
        get_turn_id=lambda: turn_id,
        get_messenger=lambda: messenger,
        get_follow_up_contexts=lambda: follow_up_contexts,
        get_graph_ref=lambda: graph_ref[0],
        get_last_apply_result=lambda: last_apply_result_ref[0],
        get_result=lambda: result,
        get_content=lambda: content,
        get_response=_get_progress_response,
        get_apply_meta=lambda: apply_meta,
        get_session_language=lambda: session.session_language,
        get_run_output=_get_run_output,
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
            cb = stream_callback
            if callable(cb):
                cb(inline_status_stream_chunk(INLINE_STATUS_FOR_STREAMING))
        except (TypeError, ValueError):
            # bad arguments or chunk type mismatch
            return

    def _maybe_thinking_off() -> None:
        try:
            cb = stream_callback
            if callable(cb):
                cb(inline_status_stream_chunk(None))
        except (TypeError, ValueError):
            return

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

    raw_history = context.get("history")

    history: AgentChatHistory = (
        list(raw_history)
        if isinstance(raw_history, list)
        else []
    )

    session_language = str(context.get("session_language") or "")
    raw_last_apply_result = context.get("last_apply_result")

    last_apply_result: AgentApplyWorkflowEditsResult | None = (
        AgentApplyWorkflowEditsResult.model_validate(raw_last_apply_result)
        if raw_last_apply_result is not None
        else None
    )

    initial_graph_md5 = graph_md5(graph) if isinstance(graph, dict) else None
    raw_recent_changes = context.get("recent_changes")

    recent_changes: str | None = (
        raw_recent_changes
        if isinstance(raw_recent_changes, str)
        else None
    )

    coding_is_allowed = bool(context.get("coding_is_allowed", True))
    contribution_is_allowed = bool(context.get("contribution_is_allowed", False))

    timeout_s = context.get("timeout_s")
    if timeout_s is None:
        timeout_s = context.get("orchestrator_timeout_s")

    # ── Mutable references ──
    graph_ref: list[ProcessGraph] = [graph]
    last_apply_result_ref: list[AgentApplyWorkflowEditsResult | None] = [last_apply_result]
    wf_language_hint: list[str] = [default_wf_language_hint(session_language)]
    session = SessionProxy(session_language=session_language, history=history)

    # ── Role resolution ──
    try:
        role_config = get_role(role_id)
    except (FileNotFoundError, KeyError, ValueError, TypeError):
        role_id = WORKFLOW_DESIGNER_ROLE_ID

        try:
            role_config = get_role(role_id)
        except (FileNotFoundError, KeyError, ValueError, TypeError) as exc:
            return {
                "status": None,
                "token": None,
                "message": None,
                "role": None,
                "error": {
                    "type": "error",
                    "error": f"Role config failed: {exc}",
                },
            }

    agent_display = role_config.role_name or role_id


    # ── graph_summary override ──
    try:
        from agents.chat.context.todo_list_manager import get_summary_params

        graph_value = coerce_graph(graph)

        graph_for_summary: ProcessGraph | None = (
            ProcessGraph.model_validate(graph_value)
            if graph_value is not None
            else None
        )

        raw_overrides = role_config.chat_overrides

        if isinstance(raw_overrides, dict):
            overrides: dict[str, object] = dict(raw_overrides)
        else:
            overrides = {}

        if role_config.light_graph_mode:
            overrides["graph_summary"] = {
                "include_code_block_source": False,
                "include_structure": False,
            }
        else:
            overrides["graph_summary"] = get_summary_params(
                coding_is_allowed,
                graph_for_summary,
            )

        role_config = replace(
            role_config,
            chat_overrides=overrides,
        )

    except (ImportError, KeyError, TypeError, ValueError, ValidationError):
        pass

    turn_id = new_id()
    follow_up_contexts: list[str] = []

    light_graph_mode = role_config.light_graph_mode

    # ── Build initial workflow inputs ──
    initial_inputs = await build_initial_inputs(
        user_message,
        graph,
        last_apply_result,
        recent_changes,
        session_language,
        history,
        wf_language_hint[0],
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        light_graph_mode=light_graph_mode,
    )

    # ── Run main workflow ──
    try:
        _maybe_thinking_on()

        raw_overrides = role_config.chat_overrides

        param_overrides: WorkflowInputs | None = (
            as_workflow_inputs(to_json_value(raw_overrides))
            if raw_overrides is not None
            else None
        )

        workflow_path_value = role_config.chat_workflow

        if workflow_path_value is not None and not isinstance(
            workflow_path_value,
            (str, Path),
        ):
            raise TypeError("chat_workflow must be a string, Path, or None")

        workflow_path: str | Path | None = workflow_path_value

        raw_timeout = timeout_s

        if raw_timeout is not None and not isinstance(
            raw_timeout,
            (int, float),
        ):
            raise TypeError("timeout_s must be a number or None")

        timeout: float | None = (
            float(raw_timeout)
            if raw_timeout is not None
            else None
        )
        # run the agent role workflow
        if timeout_s is not None:
            response = await _await_with_log(
                "run_agent_workflow(timed)",
                asyncio.wait_for(
                    run_agent_workflow(
                        initial_inputs,
                        param_overrides,
                        None,
                        stream_callback,
                        workflow_path=workflow_path,
                    ),
                    timeout=timeout,
                ),
            )

            # --- response normalization ---
            if asyncio.iscoroutine(response):
                response = await response

            if isinstance(response, AgentWorkflowResponse):
                normalized_response = response
            elif isinstance(response, Mapping):
                normalized_response = AgentWorkflowResponse.from_dict(response)
            else:
                raise TypeError(
                    "Expected AgentWorkflowResponse or mapping, "
                    f"got {type(response).__name__}"
                )

            response = normalized_response
            # ---------------------------------------------------------------------
        else:
            response = await _await_with_log(
                "run_agent_workflow",
                run_agent_workflow(
                    initial_inputs,
                    param_overrides,
                    None,
                    stream_callback,
                    workflow_path=workflow_path,
                ),
            )
            # --- response normalization ---
            if asyncio.iscoroutine(response):
                response = await response

            if isinstance(response, AgentWorkflowResponse):
                normalized_response = response
            elif isinstance(response, Mapping):
                normalized_response = AgentWorkflowResponse.from_dict(response)
            else:
                raise TypeError(
                    "Expected AgentWorkflowResponse or mapping, "
                    f"got {type(response).__name__}"
                )

            response = normalized_response
            # ---------------------------------------------------------------------

    except WorkflowTimeoutError as ex:
        _maybe_thinking_off()

        timeout_s2 = getattr(ex, "timeout_s", 300)
        content = (
            f"(Request timed out after {timeout_s2:.0f}s. "
            "Try again or check that the LLM/service is responding.)"
        )

        result = {
            "kind": "parse_error",
            "content_for_display": content,
            "apply_result": None,
            "edits": [],
        }

        last_apply_result_ref[0] = None
        await _checkpoint("after:WorkflowTimeoutError")

        followup_error = {
            "type": "WorkflowTimeoutError",
            "error": str(ex),
        }

    except (ValueError, TypeError, RuntimeError) as exc:
        _maybe_thinking_off()

        content = f"(Workflow error: {exc})"
        result = {
            "kind": "parse_error",
            "content_for_display": content,
            "apply_result": None,
            "edits": [],
        }

        last_apply_result_ref[0] = None
        await _checkpoint("after:WorkflowException")

        followup_error = {
            "type": type(exc).__name__,
            "error": str(exc),
        }


    else:
        # ---stop inline status "Thinking" ---
        _maybe_thinking_off()

        try:
            await _checkpoint("before:maybe_pin_session_language")
            maybe_pin_session_language_from_workflow_response(session, response)
            wf_language_hint[0] = default_wf_language_hint(session.session_language)
            await _checkpoint("after:maybe_pin_session_language")

            # ── Check delegation ──
            await _checkpoint("before:delegate_check")

            def _response_field(name: str) -> object:
                if isinstance(response, Mapping):
                    return response.get(name)

                return getattr(response, name, None)

            dr_out = _response_field("delegate_request")
            if isinstance(dr_out, dict) and dr_out.get("ok") is True:
                dt = str(dr_out.get("delegate_to") or "").strip().lower()
                if dt and dt != role_id.lower():
                    # publish batch update
                    _publish_in_progress(
                            stage="turn:delegated",
                            kind=result.get("kind"),
                        )
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

            _maybe_thinking_on()

            if asyncio.iscoroutine(response):
                response = await response


            await _checkpoint("before:build_parser_follow_up_context")
            parser_ctx = build_parser_follow_up_context(
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

            async def _parser_chain_runner_async(
                resp: AgentWorkflowResponse,
            ) -> AgentWorkflowResponse:
                await _checkpoint("parser_chain_runner:enter")

                chained = await run_execution_follow_up_chain_async(parser_ctx, resp)

                await _checkpoint("parser_chain_runner:done")
                return chained if chained is not None else resp


            response = await _await_with_log(
                "parser_follow_up_chain",
                _parser_chain_runner_async(response),
            )

            await _checkpoint("before:build_content_result")

            merged_response = response.merged_response

            raw_reply: object = merged_response.reply

            if isinstance(raw_reply, dict) and "action" in raw_reply:
                raw_reply = raw_reply.get("action") or ""

            content = (
                raw_reply if isinstance(raw_reply, str) else str(raw_reply or "")
            ).strip() or "(No response from model.)"

            result = cast(ProgressResult, merged_response.result)

            edits = result.get("edits") or []

            await _checkpoint("before:set_commenter_for_new_comments")
            await set_commenter_for_new_comments(edits, agent_role_id=role_id)

            result["edits"] = edits

            last_apply_result = merged_response.result.get("last_apply_result")

            raw_apply_result: object = (
                merged_response.status
                or last_apply_result
                or result.get("apply_result")
            )

            apply_result: AgentApplyWorkflowEditsResult | None = None

            if isinstance(raw_apply_result, AgentApplyWorkflowEditsResult):
                apply_result = raw_apply_result
            elif isinstance(raw_apply_result, dict):
                try:
                    apply_result = AgentApplyWorkflowEditsResult.model_validate(
                        raw_apply_result
                    )
                except ValidationError:
                    apply_result = None

            result["apply_result"] = apply_result

            ar0 = result.get("apply_result")

            if (
                result.get("kind") != "apply_failed"
                and ar0 is not None
                and ar0.attempted
                and not ar0.success
            ):
                result["kind"] = "apply_failed"

            result["content_for_display"] = content

            last_apply_result_ref[0] = apply_result

            await _checkpoint("after:build_content_result")

            _publish_in_progress(
                stage="turn:workflow_completed",
                kind=result.get("kind"),
            )

            await _checkpoint("before:handle_kind_branch")

            if result.get("kind") == "applied" and result.get("graph") is not None:
                await _checkpoint("branch:applied")

                graph_to_apply = result.get("graph")

                if result.get("kind") == "applied" and graph_to_apply is not None:
                    await _checkpoint("branch:applied")

                    applied_graph, _supplements, _v_err = await _await_with_log(
                        "apply_and_augment_graph",
                        apply_and_augment_graph(
                            graph_to_apply,
                            result.get("edits") or [],
                            {"coding_is_allowed": coding_is_allowed},
                            graph_ref,
                            last_apply_result_ref,
                        ),
                    )

                    if applied_graph is not None:
                        result["graph"] = applied_graph

                        _publish_in_progress(
                            stage="turn:graph_applied",
                            kind=result.get("kind"),
                        )

                    content_holder = [content]
                    await _checkpoint("before:build_post_apply_context")
                    post_ctx = build_post_apply_context(
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

                    _edits = result.get("edits") or []

                    _todo_edits = [
                        edit
                        for edit in _edits
                        if isinstance(edit, dict) and edit.get("action") in TODO_ACTIONS
                    ]

                    had_todo_followup = any(
                        edit.get("action") != "add_todo_list"
                        for edit in _todo_edits
                    ) or graph_has_any_open_tasks(applied_graph)

                    flags = PostEditFlags(
                        had_import_workflow=any(
                            isinstance(edit, dict)
                            and edit.get("action") == IMPORT_WORKFLOW_ACTION
                            for edit in _edits
                        ),
                        had_todo=had_todo_followup,
                        had_add_comment=any(
                            isinstance(edit, dict)
                            and edit.get("action") in COMMENT_ACTIONS
                            for edit in _edits
                        ),
                    )

                    async def _parser_chain_for_post(r: AgentWorkflowResponse) -> AgentWorkflowResponse:
                        return await _parser_chain_runner_async(r)

                    await _checkpoint("before:run_post_execution_follow_up_chain_async")
                    await _await_with_log(
                        "post_apply_follow_up_rounds_async",
                        run_post_execution_follow_up_chain_async(
                            post_ctx,
                            result=result,
                            content_holder=content_holder,
                            parser_chain_runner=_parser_chain_for_post,
                            flags=flags,
                        ),
                    )
                    await _checkpoint("after:run_post_execution_follow_up_chain_async")

                    _publish_in_progress(
                        stage="turn:post_apply_completed",
                        kind=result.get("kind"),
                    )

                    content = content_holder[0]

            elif (
                result.get("kind") == "apply_failed"
                and not role_config.light_graph_mode
            ):
                await _checkpoint("branch:apply_failed")

                raw_failed_apply = (
                    result.get("last_apply_result")
                    or result.get("apply_result")
                )

                if not isinstance(raw_failed_apply, AgentApplyWorkflowEditsResult):
                    if not isinstance(raw_failed_apply, dict):
                        return {}

                    try:
                        failed_apply = AgentApplyWorkflowEditsResult(
                            **raw_failed_apply
                        )
                    except (TypeError, ValueError):
                        return {}
                else:
                    failed_apply = raw_failed_apply

                last_apply_result_ref[0] = failed_apply

                await _checkpoint("before:self_correction_retry")

                (
                    _retry_resp,
                    retry_result,
                    retry_content,
                ) = await _await_with_log(
                    "self_correction_retry_async",
                    run_self_correction_retry_async(
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

                _publish_in_progress(
                    stage="turn:self_correction_retry_completed",
                    kind=(retry_result or {}).get("kind") if "retry_result" in locals() else result.get("kind"),
                )

                if retry_result and retry_result.get("kind") == "applied" and retry_content:
                    content = content + "\n\n" + retry_content

            await _checkpoint("after:handle_kind_branch")

            # ── Finalize session language (WD only) ──
            if role_id == WORKFLOW_DESIGNER_ROLE_ID:
                await _checkpoint("before:finalize_session_language")
                finalize_workflow_designer_turn_session_language(session, response)
                await _checkpoint("after:finalize_session_language")

        except (asyncio.CancelledError, KeyboardInterrupt) as exc:
            # ensure we still build final output (incl. asyncio.CancelledError)
            _maybe_thinking_off()

            followup_error = {"type": type(exc).__name__, "error": str(exc)}
            if fallback_graph is not None:
                graph_ref[0] = fallback_graph

            content = f"(Follow-up/apply error: {type(exc).__name__}: {exc})"
            result = {
                "kind": "parse_error",
                "content_for_display": content,
                "apply_result": None,
                "edits": [],
            }
            last_apply_result_ref[0] = None
            await _checkpoint("after:followup_error_outer_handler")


    # ── Merge final graph with the most resent version ──
    merged_graph = await merge_latest_graph_for_final_output(
        graph_ref=graph_ref,
        initial_graph_md5=initial_graph_md5,
    )

    if merged_graph is not None:
        graph_ref[0] = merged_graph

    # ── Assemble final output ──
    await _checkpoint("before:assemble_final_output")

    progress_response: ProgressResponse = {}
    run_output: Data = {}
    graph_json = graph_to_json_object(graph_ref[0])

    if isinstance(response, dict):
        progress_response = {
            "llm_user_message": (
                response.get("llm_user_message")
                if isinstance(response.get("llm_user_message"), str)
                else None
            ),
            "llm_system_prompt": (
                response.get("llm_system_prompt")
                if isinstance(response.get("llm_system_prompt"), str)
                else None
            ),
        }

        raw_run_output = response.get("run_output")

        if isinstance(raw_run_output, dict):
            run_output = raw_run_output

    workflow_response: AgentWorkflowResponse | None = (
        response if isinstance(response, AgentWorkflowResponse) else None
    )

    display_content = str(result.get("content_for_display") or content)

    display_content += formulas_calc_display_appendix(
        workflow_response
    )

    apply_meta = apply_meta_with_formulas_calc_tool_status(
        workflow_response,
        result.get("apply_result", {}),
    )


    _publish_in_progress(
        stage="turn:completed",
        kind=result.get("kind"),
    )

    final_message: Data = {
        "id": new_id(),
        "ts": now_ts(),
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
        "graph": graph_json,
        "run_output": run_output,
        "follow_up_contexts": follow_up_contexts,
        "last_apply_result": last_apply_result_ref[0],
        "session_language": session.session_language,
        "messenger": messenger,
        "llm_user_message": progress_response.get("llm_user_message"),
        "llm_system_prompt": progress_response.get("llm_system_prompt"),
    }

    out = {
        "status": None,
        "token": {"type": "token", "token": display_content},
        "message": {"type": "final", "message": final_message},
        "role": {"role_id": role_id, "name": agent_display},
        "error": followup_error,
    }

    await _checkpoint("after:assemble_final_output")
    return out
