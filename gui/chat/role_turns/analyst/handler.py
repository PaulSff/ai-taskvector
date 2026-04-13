"""Analyst assistants chat turn: same pipeline as Workflow Designer without structural graph edits."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from assistants.roles import ANALYST_ROLE_ID, get_role
from assistants.roles.workflow_path import get_role_chat_workflow_path
from assistants.roles.workflow_designer.workflow_inputs import (
    build_assistant_workflow_initial_inputs,
    default_wf_language_hint,
)
from assistants.tools.catalog import ORDERED_ANALYST_TOOLS, analyst_tool_ids
from gui.chat.chat_turn_context import (
    format_previous_turn,
    normalize_user_message_for_workflow,
)
from ..turn_edits import canonicalize_add_comment_edits
from gui.chat.language_control import (
    finalize_workflow_designer_turn_session_language,
    maybe_pin_session_language_from_workflow_response,
)
from gui.chat.rag_context import _UNITS_DIR
from gui.chat.workflow_designer_followups import (
    ParserFollowUpContext,
    PostApplyFlags,
    PostApplyFollowUpContext,
    run_parser_output_follow_up_chain,
    run_post_apply_follow_up_rounds,
)
from gui.chat.llm_prompt_inspector import record_llm_prompt_view_if_present
from gui.chat.workflow_designer_handler import (
    build_assistant_workflow_unit_param_overrides,
    build_self_correction_retry_inputs,
    get_runtime_for_prompts,
    refresh_last_apply_result_after_canvas_apply,
    run_assistant_workflow,
)
from gui.components.settings import get_workflow_designer_max_follow_ups
from gui.components.workflow_tab.workflows.core_workflows import validate_graph_to_apply_for_canvas
from ..context import RoleChatTurnContext
from runtime.run import WorkflowTimeoutError

_ANALYST_WORKFLOW_PATH = get_role_chat_workflow_path(ANALYST_ROLE_ID).resolve()
_ANALYST_PROMPT_PATH = _ANALYST_WORKFLOW_PATH.parents[3] / "config" / "prompts" / "analyst.json"


class AnalystChatHandler:
    """Runs analyst_workflow.json: tools + comments/todos only (no structural graph edits)."""

    @property
    def role_id(self) -> str:
        return ANALYST_ROLE_ID

    @property
    def display_name(self) -> str:
        return get_role(ANALYST_ROLE_ID).display_name

    async def run_turn(self, turn_ctx: RoleChatTurnContext, *, message_for_workflow: str) -> None:
        response: dict[str, Any] = {}
        content = ""
        result: dict[str, Any] = {}

        overrides = build_assistant_workflow_unit_param_overrides(
            turn_ctx.provider,
            turn_ctx.cfg,
            report_output_dir=str(Path(turn_ctx.mydata_dir) / "reports"),
            prompt_template_path=_ANALYST_PROMPT_PATH,
            llm_options_role_id=ANALYST_ROLE_ID,
            rag_top_k_role_id=ANALYST_ROLE_ID,
        )
        overrides["graph_summary"] = {
            "include_code_block_source": False,
            "include_structure": False,
        }

        _graph = turn_ctx.graph_ref[0]
        follow_up_contexts_this_turn: list[str] = []
        wf_lang_cell = [default_wf_language_hint(turn_ctx.state.session_language)]
        _an_role = get_role(ANALYST_ROLE_ID)
        max_follow_ups = (
            _an_role.follow_up_max_rounds
            if _an_role.follow_up_max_rounds is not None
            else get_workflow_designer_max_follow_ups()
        )
        follow_up_tools = _an_role.tools if _an_role.tools else tuple(analyst_tool_ids())

        async def _parser_output_follow_up_chain(resp: dict[str, Any]) -> dict[str, Any] | None:
            parser_ctx = ParserFollowUpContext(
                page=turn_ctx.page,
                graph_ref=turn_ctx.graph_ref,
                state=turn_ctx.state,
                token=turn_ctx.token,
                turn_id=turn_ctx.turn_id,
                assistant_label=turn_ctx.assistant_display,
                follow_up_contexts=follow_up_contexts_this_turn,
                max_rounds=max_follow_ups,
                wf_language_hint=wf_lang_cell,
                is_current_run=turn_ctx.is_current_run,
                toast=lambda m: turn_ctx.toast(m),
                set_inline_status=turn_ctx.set_inline_status,
                append_message=turn_ctx.append_message,
                prepare_stream_row=turn_ctx.prepare_stream_row,
                normalize_user_message_for_workflow=normalize_user_message_for_workflow,
                last_apply_result_ref=turn_ctx.last_apply_result_ref,
                get_recent_changes=turn_ctx.get_recent_changes,
                overrides=overrides,
                run_workflow_streaming=turn_ctx.run_workflow_streaming,
                get_runtime_for_prompts=get_runtime_for_prompts,
                format_previous_turn=format_previous_turn,
                on_show_run_console=turn_ctx.on_show_run_console,
                follow_up_tool_ids=follow_up_tools,
                follow_up_source_response=None,
                assistant_role_id=ANALYST_ROLE_ID,
                assistant_workflow_path=_ANALYST_WORKFLOW_PATH,
                analyst_mode=True,
                ordered_follow_up_tools=ORDERED_ANALYST_TOOLS,
                record_llm_prompt_view=turn_ctx.record_llm_prompt_view,
            )
            return await run_parser_output_follow_up_chain(parser_ctx, resp)

        try:
            turn_ctx.prepare_stream_row()
            last_user_content = None
            for m in reversed(turn_ctx.state.history or []):
                if isinstance(m, dict) and (m.get("role") or "").strip().lower() == "user":
                    last_user_content = (m.get("content") or m.get("content_for_display") or "")
                    break
            user_message_for_workflow = normalize_user_message_for_workflow(
                last_user_content if (last_user_content is not None and str(last_user_content).strip()) else message_for_workflow
            )
            _runtime = get_runtime_for_prompts(_graph)
            initial_inputs = build_assistant_workflow_initial_inputs(
                user_message_for_workflow,
                _graph,
                turn_ctx.last_apply_result_ref[0],
                turn_ctx.get_recent_changes() if turn_ctx.get_recent_changes else None,
                runtime=_runtime,
                coding_is_allowed=turn_ctx.coding_is_allowed,
                contribution_is_allowed=turn_ctx.contribution_is_allowed,
                previous_turn=format_previous_turn(turn_ctx.state.history[:-1]),
                language_hint=wf_lang_cell[0],
                session_language=turn_ctx.state.session_language,
                analyst_mode=True,
            )
            response = await turn_ctx.run_workflow_streaming(
                run_assistant_workflow,
                initial_inputs,
                overrides,
                None,
                _run_token=turn_ctx.token,
                workflow_path=_ANALYST_WORKFLOW_PATH,
            )
        except WorkflowTimeoutError as ex:
            turn_ctx.set_inline_status(None)
            response = {"reply": "", "workflow_errors": []}
            content = f"(Request timed out after {getattr(ex, 'timeout_s', 300):.0f}s. Try again or check that the LLM/service is responding.)"
            result = {"kind": "parse_error", "content_for_display": content, "apply_result": {}, "edits": []}
            turn_ctx.last_apply_result_ref[0] = None
        except Exception as ex:
            turn_ctx.set_inline_status(None)
            response = {"reply": "", "workflow_errors": []}
            content = f"(Workflow error: {ex})"
            result = {"kind": "parse_error", "content_for_display": content, "apply_result": {}, "edits": []}
            turn_ctx.last_apply_result_ref[0] = None
        else:
            chained = await _parser_output_follow_up_chain(response)
            if chained is None:
                return
            response = chained

            report_out = response.get("report_output")
            if (
                turn_ctx.is_current_run(turn_ctx.token)
                and isinstance(report_out, dict)
                and report_out.get("ok")
            ):
                turn_ctx.set_inline_status("Making report…")
                try:
                    from gui.components.settings import get_rag_update_workflow_path
                    from runtime.run import run_workflow

                    path = get_rag_update_workflow_path()
                    if path.exists():
                        overrides_rag = {
                            "rag_update": {
                                "rag_index_data_dir": str(turn_ctx.rag_index_dir),
                                "units_dir": str(_UNITS_DIR),
                                "mydata_dir": str(turn_ctx.mydata_dir),
                                "embedding_model": turn_ctx.rag_embedding_model,
                            },
                        }
                        await asyncio.to_thread(
                            run_workflow,
                            path,
                            initial_inputs={},
                            unit_param_overrides=overrides_rag,
                            format="dict",
                        )
                except Exception:
                    pass
                if turn_ctx.is_current_run(turn_ctx.token):
                    turn_ctx.set_inline_status(None)

            raw_reply = response.get("reply")
            if isinstance(raw_reply, dict) and "action" in raw_reply:
                raw_reply = raw_reply.get("action") or ""
            content = (raw_reply if isinstance(raw_reply, str) else str(raw_reply or "")).strip() or "(No response from model.)"
            if content == "(No response from model.)":
                po = response.get("parser_output")
                edits = po if isinstance(po, list) else (po.get("edits") if isinstance(po, dict) else None)
                if isinstance(edits, list) and edits:
                    content = "No tool actions requested."
            wf_result = response.get("result") or {}
            result = dict(wf_result)
            canonicalize_add_comment_edits(result.get("edits"), assistant_role_id=turn_ctx.profile)
            result["apply_result"] = response.get("status") or wf_result.get("last_apply_result") or {}
            ar0 = result.get("apply_result") or {}
            if (
                result.get("kind") != "apply_failed"
                and isinstance(ar0, dict)
                and ar0.get("attempted") is True
                and ar0.get("success") is False
            ):
                result["kind"] = "apply_failed"
            workflow_errors = response.get("workflow_errors") or []
            user_message_missing = any(
                err
                and (
                    (str(err[0]) == "llm_agent" and (err[1] or "").strip())
                    or "placeholder" in (err[1] or "").lower()
                    or "no message" in (err[1] or "").lower()
                )
                for err in workflow_errors
            )
            if user_message_missing:
                content = "Your message didn't reach the model. Please try sending again."
                result["content_for_display"] = content
            else:
                result["content_for_display"] = content
            turn_ctx.last_apply_result_ref[0] = wf_result.get("last_apply_result")
            if workflow_errors and turn_ctx.is_current_run(turn_ctx.token):
                err_msg = workflow_errors[0][1][:150] if workflow_errors else ""
                if len(workflow_errors) > 1:
                    err_msg += f" (+{len(workflow_errors) - 1} more)"
                if user_message_missing:
                    await turn_ctx.toast("Your message didn't reach the model. Please try again.")
                else:
                    await turn_ctx.toast(f"Workflow error: {err_msg}")

        display_content = result.get("content_for_display", content) or content
        meta = {
            "turn_id": turn_ctx.turn_id,
            "assistant": turn_ctx.assistant_display,
            "source": "assistant_response",
            "workflow_response": {"reply": content, "result_kind": result.get("kind")},
            "parsed_edits": result.get("edits", []),
            "apply": result.get("apply_result", {}),
        }
        if result.get("kind") == "parse_error":
            meta["format_error"] = True
        if follow_up_contexts_this_turn:
            meta["follow_up_contexts"] = follow_up_contexts_this_turn
        turn_ctx.append_message("assistant", display_content, meta=meta)

        if not turn_ctx.is_current_run(turn_ctx.token):
            return
        turn_ctx.set_inline_status(None)

        apply_fn = turn_ctx.apply_from_assistant if turn_ctx.apply_from_assistant else turn_ctx.set_graph
        if result.get("kind") == "applied" and result.get("graph") is not None:
            graph_to_apply = result["graph"]
            _client_todo_supplements: list[str] = []
            if isinstance(graph_to_apply, dict):
                from gui.chat.todo_list_manager import augment_graph_with_client_tasks

                graph_to_apply, extra_supp = augment_graph_with_client_tasks(
                    graph_to_apply,
                    result.get("edits") or [],
                    coding_is_allowed=turn_ctx.coding_is_allowed,
                )
                _client_todo_supplements.extend(extra_supp)
            applied_ok = False
            if isinstance(graph_to_apply, dict):
                vg, v_err = validate_graph_to_apply_for_canvas(graph_to_apply)
                if v_err or vg is None:
                    graph_to_apply = None
                    if turn_ctx.is_current_run(turn_ctx.token):
                        await turn_ctx.toast(
                            f"Could not validate graph: {(v_err or '')[:120]}",
                        )
                else:
                    graph_to_apply = vg
            if graph_to_apply is not None:
                apply_fn(graph_to_apply)
                turn_ctx.last_apply_result_ref[0] = refresh_last_apply_result_after_canvas_apply(
                    turn_ctx.last_apply_result_ref[0],
                    turn_ctx.graph_ref[0],
                    supplement_summary="; ".join(_client_todo_supplements),
                )
                await turn_ctx.toast("Applied")
                applied_ok = True
            if applied_ok:
                had_import_workflow = any(
                    e.get("action") == "import_workflow"
                    for e in result.get("edits", [])
                )
                _TODO_ACTIONS = frozenset({"add_todo_list", "remove_todo_list", "add_task", "remove_task", "mark_completed"})
                had_todo = any(e.get("action") in _TODO_ACTIONS for e in result.get("edits", []))
                had_add_comment = any(e.get("action") == "add_comment" for e in result.get("edits", []))
                content_holder = [content]
                post_ctx = PostApplyFollowUpContext(
                    graph_ref=turn_ctx.graph_ref,
                    state=turn_ctx.state,
                    token=turn_ctx.token,
                    turn_id=turn_ctx.turn_id,
                    assistant_role_id=turn_ctx.profile,
                    assistant_label=turn_ctx.assistant_display,
                    max_rounds=max_follow_ups,
                    wf_language_hint=wf_lang_cell,
                    is_current_run=turn_ctx.is_current_run,
                    toast=lambda m: turn_ctx.toast(m),
                    set_inline_status=turn_ctx.set_inline_status,
                    append_message=turn_ctx.append_message,
                    prepare_stream_row=turn_ctx.prepare_stream_row,
                    normalize_user_message_for_workflow=normalize_user_message_for_workflow,
                    last_apply_result_ref=turn_ctx.last_apply_result_ref,
                    get_recent_changes=turn_ctx.get_recent_changes,
                    overrides=overrides,
                    run_workflow_streaming=turn_ctx.run_workflow_streaming,
                    get_runtime_for_prompts=get_runtime_for_prompts,
                    format_previous_turn=format_previous_turn,
                    replace_assistant_message_row=turn_ctx.replace_assistant_message_row,
                    stream_buffer_ref=turn_ctx.stream_buffer_ref,
                    apply_fn=apply_fn,
                    assistant_workflow_path=_ANALYST_WORKFLOW_PATH,
                    analyst_mode=True,
                    record_llm_prompt_view=turn_ctx.record_llm_prompt_view,
                )
                await run_post_apply_follow_up_rounds(
                    post_ctx,
                    result=result,
                    content_holder=content_holder,
                    parser_chain_runner=_parser_output_follow_up_chain,
                    flags=PostApplyFlags(
                        had_import_workflow=had_import_workflow,
                        had_todo=had_todo,
                        had_add_comment=had_add_comment,
                    ),
                )
                content = content_holder[0]
        elif result.get("kind") == "apply_failed":
            failed_apply = result.get("last_apply_result") or result.get("apply_result") or {}
            turn_ctx.last_apply_result_ref[0] = failed_apply
            err_str = str(failed_apply.get("error", "Unknown"))[:500]
            await turn_ctx.toast(
                f"Could not apply edits: {err_str[:120]}",
            )
            if turn_ctx.is_current_run(turn_ctx.token):
                turn_ctx.set_inline_status("Retrying with error context…")
                try:
                    _graph = turn_ctx.graph_ref[0]
                    retry_inputs = build_self_correction_retry_inputs(
                        turn_ctx.last_apply_result_ref[0],
                        _graph,
                        turn_ctx.get_recent_changes() if turn_ctx.get_recent_changes else None,
                        runtime=get_runtime_for_prompts(_graph),
                        coding_is_allowed=turn_ctx.coding_is_allowed,
                        contribution_is_allowed=turn_ctx.contribution_is_allowed,
                        previous_turn=format_previous_turn(turn_ctx.state.history),
                        language_hint=wf_lang_cell[0],
                        session_language=turn_ctx.state.session_language,
                        analyst_mode=True,
                    )
                    turn_ctx.prepare_stream_row()
                    retry_response = await turn_ctx.run_workflow_streaming(
                        run_assistant_workflow,
                        retry_inputs,
                        overrides,
                        None,
                        _run_token=turn_ctx.token,
                        workflow_path=_ANALYST_WORKFLOW_PATH,
                    )
                    record_llm_prompt_view_if_present(
                        retry_response, turn_ctx.record_llm_prompt_view
                    )
                    maybe_pin_session_language_from_workflow_response(turn_ctx.state, retry_response)
                    wf_lang_cell[0] = default_wf_language_hint(turn_ctx.state.session_language)
                    if not turn_ctx.is_current_run(turn_ctx.token):
                        return
                    r_result = (retry_response.get("result") or {})
                    canonicalize_add_comment_edits(r_result.get("edits"), assistant_role_id=turn_ctx.profile)
                    r_kind = r_result.get("kind")
                    if r_kind == "applied" and r_result.get("graph") is not None:
                        graph_to_apply = r_result["graph"]
                        if isinstance(graph_to_apply, dict):
                            from gui.chat.todo_list_manager import augment_graph_with_client_tasks

                            graph_to_apply, _retry_supp = augment_graph_with_client_tasks(
                                graph_to_apply,
                                r_result.get("edits") or [],
                                coding_is_allowed=turn_ctx.coding_is_allowed,
                            )
                            vg, v_err = validate_graph_to_apply_for_canvas(graph_to_apply)
                            if v_err or vg is None:
                                graph_to_apply = None
                                if turn_ctx.is_current_run(turn_ctx.token):
                                    await turn_ctx.toast(
                                        f"Retry graph validation failed: {(v_err or '')[:100]}",
                                    )
                            else:
                                graph_to_apply = vg
                        if graph_to_apply is not None:
                            apply_fn(graph_to_apply)
                            await turn_ctx.toast("Applied (after retry)")
                            retry_reply = (retry_response.get("reply") or "").strip()
                            if retry_reply:
                                content = content + "\n\n" + retry_reply
                                result["content_for_display"] = content
                                turn_ctx.append_message(
                                    "assistant",
                                    retry_reply,
                                    meta={
                                        "turn_id": turn_ctx.turn_id,
                                        "assistant": turn_ctx.assistant_display,
                                        "source": "assistant_response",
                                        "workflow_response": {"reply": retry_reply, "result_kind": "applied"},
                                    },
                                )
                            turn_ctx.last_apply_result_ref[0] = r_result.get("last_apply_result")
                    elif r_kind == "apply_failed":
                        turn_ctx.last_apply_result_ref[0] = r_result.get("last_apply_result") or r_result.get("apply_result")
                        await turn_ctx.toast(f"Retry also failed: {str(r_result.get('apply_result', {}).get('error', 'Unknown'))[:80]}")
                except Exception:
                    pass
                turn_ctx.set_inline_status(None)
        finalize_workflow_designer_turn_session_language(
            turn_ctx.state, response, debug_log=turn_ctx.workflow_debug_log
        )
        turn_ctx.persist_history_debounced()
        return
