"""Workflow Designer agents chat turn (extracted from ``chat.py``)."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

from pydantic import ValidationError

from agents.chat.agent_workflow import (
    AgentWorkflowResponse,
    MergeResponse,
    build_agent_workflow_unit_param_overrides,
    build_self_correction_retry_inputs,
    get_runtime_for_prompts,
    normalize_last_apply_result,
    refresh_last_graph_apply_result,
    run_agent_workflow,
)
from agents.chat.agent_workflow.helpers import (
    get_optional_str,
    validate_graph_to_apply_inline,
)
from agents.chat.context.follow_up_context import (
    ParserFollowUpContext,
    PostApplyFlags,
    PostApplyFollowUpContext,
)
from agents.chat.context.language_control import (
    finalize_workflow_designer_turn_session_language,
    maybe_pin_session_language_from_workflow_response,
)
from agents.chat.context.llm_prompt_inspector import record_llm_prompt_view_if_present
from agents.chat.context.todo_list_manager import get_summary_params
from agents.chat.handlers.auto_delegate_turn import try_run_auto_delegate_before_turn
from agents.chat.handlers.chat_turn_context import (
    format_previous_turn,
    normalize_user_message_for_workflow,
)
from agents.chat.parser_follow_up import (
    run_parser_output_follow_up_chain_async,
    run_post_apply_follow_up_rounds_async,
)
from agents.chat.utils.workflow_output_normalizer import (
    apply_meta_with_formulas_calc_tool_status,
    formulas_calc_display_appendix,
)
from agents.roles import WORKFLOW_DESIGNER_ROLE_ID, get_role
from agents.roles.types import RoleConfig
from agents.roles.workflow_designer.workflow_inputs import (
    build_agent_workflow_initial_inputs,
    default_wf_language_hint,
)
from agents.roles.workflow_path import get_role_chat_workflow_path
from agents.tools.catalog import ordered_tools_for_role_id
from agents.tools.types import ParsedActions
from core.schemas import ProcessGraph
from core.schemas.graph_edit_api import (
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
    GraphEditAction,
    MultipleEditsSequential,
)
from core.schemas.primitives import (
    Data,
    ModelDumpable,
    WorkflowInputs,
    is_data,
)
from gui.components.settings import get_workflow_designer_max_follow_ups
from gui.components.settings.paths import UNITS_DIR
from runtime.run import WorkflowTimeoutError

from ..context import RoleChatTurnContext
from ..turn_edits import set_commenter_for_new_comments

_WORKFLOW_DESIGNER_WORKFLOW_PATH = (
    get_role_chat_workflow_path(WORKFLOW_DESIGNER_ROLE_ID).resolve()
)

_WORKFLOW_DESIGNER_PROMPT_PATH = (
    _WORKFLOW_DESIGNER_WORKFLOW_PATH.parents[3]
    / "config"
    / "prompts"
    / "workflow_designer.json"
)

_WORKFLOW_EXECUTION_TIMEOUT = None # default

# actions supported:
IMPORT_WORKFLOW_ACTION: GraphEditAction = "import_workflow"
ADD_COMMENT_ACTION: GraphEditAction = "add_comment"

TODO_ACTIONS: frozenset[GraphEditAction] = frozenset(
    {
        "add_todo_list",
        "remove_todo_list",
        "add_task",
        "remove_task",
        "mark_completed",
    }
)

class WorkflowDesignerChatHandler:
    """Runs one Workflow Designer's turn."""

    @property
    def role_id(self) -> str:
        return WORKFLOW_DESIGNER_ROLE_ID

    @property
    def role_name(self) -> str:
        return get_role(self.role_id).role_name


    async def run_turn(
        self,
        turn_ctx: RoleChatTurnContext,
        *,
        message_for_workflow: str,
    ) -> None:
        response = AgentWorkflowResponse()
        content = ""
        result: Data = {}

        role_cfg: RoleConfig = get_role(self.role_id)

        overrides: WorkflowInputs = (
            build_agent_workflow_unit_param_overrides(
                provider=role_cfg.provider,
                report_output_dir=str(
                    Path(turn_ctx.mydata_dir) / "reports"
                ),
                model_name=role_cfg.ollama_model,
                host=role_cfg.ollama_host,
                llm_options_role_id=self.role_id,
                rag_top_k_role_id=self.role_id,
            )
        )

        _graph: ProcessGraph = turn_ctx.graph_ref[0]

        validated_graph, validation_error = (
            await validate_graph_to_apply_inline(_graph)
        )

        if validation_error is not None:
            raise ValueError(validation_error)

        _graph_dict = (
            validated_graph.model_dump(by_alias=True)
            if validated_graph is not None
            else None
        )

        overrides["graph_summary"] = get_summary_params(
            turn_ctx.coding_is_allowed,
            validated_graph,
        )

        def _failed_apply_result(
            error: str,
            *,
            attempted: bool = True,
        ) -> AgentApplyWorkflowEditsResult:
            return AgentApplyWorkflowEditsResult(
                attempted=attempted,
                apply_result=ApplyWorkflowEditsResult(
                    success=False,
                    graph=_graph,
                    error=error,
                ),
                edits_summary="No workflow edits were applied.",
            )

        follow_up_contexts_this_turn: list[str] = []
        wf_lang_cell = [default_wf_language_hint(turn_ctx.state.session_language)]
        _wd_role = get_role(WORKFLOW_DESIGNER_ROLE_ID)
        max_wd_follow_ups = (
            _wd_role.follow_up_max_rounds
            if _wd_role.follow_up_max_rounds is not None
            else get_workflow_designer_max_follow_ups()
        )
        wd_follow_up_tools = (
            _wd_role.tools if _wd_role.tools else tuple(
                tid for tid, _ in ordered_tools_for_role_id(WORKFLOW_DESIGNER_ROLE_ID)
            )
        )

        async def _parser_output_follow_up_chain(
            resp: AgentWorkflowResponse,
        ) -> AgentWorkflowResponse | None:
            parser_ctx = ParserFollowUpContext(
                page=turn_ctx.page,
                graph_ref=turn_ctx.graph_ref,
                state=turn_ctx.state,
                token=turn_ctx.token,
                turn_id=turn_ctx.turn_id,
                agent_label=turn_ctx.agent_display,
                follow_up_contexts=follow_up_contexts_this_turn,
                max_rounds=max_wd_follow_ups,
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
                follow_up_tool_ids=wd_follow_up_tools,
                follow_up_source_response=None,
                agent_role_id=WORKFLOW_DESIGNER_ROLE_ID,
                record_llm_prompt_view=turn_ctx.record_llm_prompt_view,
            )
            return await run_parser_output_follow_up_chain_async(parser_ctx, resp)

        try:
            # Use last user message from history as source of truth so the model always gets what was actually sent (avoids closure/async losing the message).
            last_user_content: str | None = None

            for m in reversed(turn_ctx.state.history or []):
                if str(m.get("role", "")).strip().lower() == "user":
                    content = m.get("content") or m.get("content_for_display") or ""
                    last_user_content = str(content)
                    break

            user_message_for_workflow = normalize_user_message_for_workflow(
                last_user_content
                if (last_user_content is not None and str(last_user_content).strip())
                else message_for_workflow
            )
            if await try_run_auto_delegate_before_turn(
                turn_ctx.delegate_request_ref,
                user_message_for_workflow,
                current_role_id=turn_ctx.profile,
            ):
                turn_ctx.set_inline_status(None)
                return
            # Show streaming bubble immediately so user sees tokens as they generate.
            turn_ctx.prepare_stream_row()
            # Language for injects: use pinned session_language or default until the first
            # workflow response supplies merge_response.language (see maybe_pin_session_language_from_workflow_response).
            _runtime = await get_runtime_for_prompts(_graph)

            initial_inputs = build_agent_workflow_initial_inputs(
                user_message_for_workflow,
                _graph,
                turn_ctx.last_apply_result_ref[0],
                turn_ctx.get_recent_changes() if turn_ctx.get_recent_changes else None,
                runtime=_runtime,
                coding_is_allowed=turn_ctx.coding_is_allowed,
                contribution_is_allowed=turn_ctx.contribution_is_allowed,
                previous_turn=await format_previous_turn(turn_ctx.state.history[:-1]),
                language_hint=wf_lang_cell[0],
                session_language=turn_ctx.state.session_language,
            )
            # Run the Workflow Designer workflow with queue-based streaming.
            response = await turn_ctx.run_workflow_streaming(
                run_agent_workflow,
                initial_inputs,
                overrides,
                _WORKFLOW_EXECUTION_TIMEOUT,
                _run_token=turn_ctx.token,
                workflow_path=_WORKFLOW_DESIGNER_WORKFLOW_PATH,
            )

            merged = response.merged_response

            dr_out = merged.delegate_request
            report_out = merged.report_output
            raw_reply = merged.reply

        except WorkflowTimeoutError as ex:
            turn_ctx.set_inline_status(None)

            content = (
                f"(Request timed out after "
                f"{getattr(ex, 'timeout_s', 300):.0f}s. "
                "Try again or check that the LLM/service is responding.)"
            )

            response = AgentWorkflowResponse(
                merged_response=MergeResponse(
                    reply="",
                    result={
                        "kind": "parse_error",
                        "content_for_display": content,
                        "apply_result": {},
                        "edits": [],
                    },
                )
            )

            result = response.merged_response.result
            turn_ctx.last_apply_result_ref[0] = _failed_apply_result(content)

        except TypeError as ex:
            turn_ctx.set_inline_status(None)
            content = f"(Workflow error: {ex})"

            response = AgentWorkflowResponse(
                merged_response=MergeResponse(
                    reply="",
                    result={
                        "kind": "parse_error",
                        "content_for_display": content,
                        "apply_result": {},
                        "edits": [],
                    },
                )
            )

            result = response.merged_response.result
            turn_ctx.last_apply_result_ref[0] = _failed_apply_result(content)

        else:
            chained = await _parser_output_follow_up_chain(response)
            if chained is None:
                return

            response = chained
            merged = response.merged_response
            result = merged.result

            dr_out = merged.delegate_request

            if turn_ctx.delegate_request_ref is not None:
                delegate_to = get_optional_str(dr_out, "delegate_to")
                error_message = get_optional_str(dr_out, "error")

                if (
                    dr_out.get("ok") is True
                    and delegate_to
                    and delegate_to.strip()
                ):
                    dt = delegate_to.strip().lower()

                    if dt != (turn_ctx.profile or "").strip().lower():
                        turn_ctx.delegate_request_ref[0] = dr_out
                else:
                    if (
                        error_message
                        and turn_ctx.is_current_run(turn_ctx.token)
                    ):
                        await turn_ctx.toast(error_message.strip()[:200])

            report_out = merged.report_output

            if (
                turn_ctx.is_current_run(turn_ctx.token)
                and report_out.get("ok")
            ):
                turn_ctx.set_inline_status("Generating file…")
                try:
                    from gui.components.settings import get_rag_update_workflow_path
                    from runtime.run import run_workflow

                    path = get_rag_update_workflow_path()
                    if path.exists():
                        overrides_rag: WorkflowInputs = {
                            "rag_update": {
                                "rag_index_data_dir": str(turn_ctx.rag_index_dir),
                                "units_dir": str(UNITS_DIR),
                                "mydata_dir": str(turn_ctx.mydata_dir),
                                "embedding_model": turn_ctx.rag_embedding_model,
                            },
                        }
                        _ = await asyncio.to_thread(
                            run_workflow,
                            path,
                            initial_inputs={},
                            unit_param_overrides=overrides_rag,
                            format="dict",
                        )
                except (TypeError, WorkflowTimeoutError):
                    pass
                if turn_ctx.is_current_run(turn_ctx.token):
                    turn_ctx.set_inline_status(None)

            raw_reply: str = merged.reply
            content = raw_reply.strip() or "(No response from the model.)"

            # If reply is empty but parser produced edits (e.g. no_edit), show a fallback
            # so chat doesn't look broken.
            # If reply is empty but parser produced edits (e.g. no_edit), show a fallback
            # so chat doesn't look broken.
            if content == "(No response from the model.)":
                parser_output = merged.parser_output
                edits = (
                    parser_output.actions.edits
                    if parser_output is not None
                    else []
                )

                if edits:
                    content = "No graph changes requested."

            wf_result = merged.result

            if merged.parser_output is not None:
                await set_commenter_for_new_comments(
                    merged.parser_output.actions.edits,
                    agent_role_id=turn_ctx.profile,
                )

            result["apply_result"] = (
                merged.status.get("last_apply_result")
                or wf_result.get("last_apply_result")
                or {}
            )

            apply_result_value = result.get("apply_result")

            if is_data(apply_result_value):
                apply_result = apply_result_value
            else:
                apply_result = {}

            if (
                result.get("kind") != "apply_failed"
                and apply_result.get("attempted") is True
                and apply_result.get("success") is False
            ):
                result["kind"] = "apply_failed"



            workflow_errors = merged.workflow_errors

            # Only treat as "message didn't reach model" when LLMAgent reported it
            # or the error text clearly says so.
            # Aggregate can emit "required... user_message" even when the message
            # did reach the model, e.g. keys param in_0 vs user_message.
            user_message_missing = any(
                err
                and (
                    (
                        str(err[0]) == "llm_agent"
                        and (err[1] or "").strip()
                    )
                    or "placeholder" in (err[1] or "").lower()
                    or "no message" in (err[1] or "").lower()
                )
                for err in workflow_errors
            )

            if user_message_missing:
                content = (
                    "Your message didn't reach the model. Please try sending again."
                )

            result["content_for_display"] = content


            # Ensure later retry/self-correction receives a valid
            # AgentApplyWorkflowEditsResult, never an awaitable or raw graph.
            ap = wf_result.get("last_apply_result")

            if inspect.isawaitable(ap):
                # Do not store an awaitable or overwrite the last valid result.
                pass

            elif isinstance(ap, AgentApplyWorkflowEditsResult):
                turn_ctx.last_apply_result_ref[0] = ap

            elif isinstance(ap, ApplyWorkflowEditsResult):
                turn_ctx.last_apply_result_ref[0] = (
                    AgentApplyWorkflowEditsResult(
                        attempted=True,
                        apply_result=ap,
                        edits_summary="",
                    )
                )

            elif isinstance(ap, ProcessGraph):
                # Backward compatibility for callers that still return a raw graph.
                turn_ctx.last_apply_result_ref[0] = (
                    AgentApplyWorkflowEditsResult(
                        attempted=True,
                        apply_result=ApplyWorkflowEditsResult(
                            success=True,
                            graph=ap,
                            error=None,
                        ),
                        edits_summary="",
                    )
                )

            elif isinstance(ap, dict):
                try:
                    parsed_result = (
                        AgentApplyWorkflowEditsResult.model_validate(ap)
                    )
                except ValidationError:
                    # Backward compatibility for an inner result dictionary.
                    try:
                        parsed_inner_result = (
                            ApplyWorkflowEditsResult.model_validate(ap)
                        )
                    except ValidationError:
                        # Invalid result: preserve the previous valid result.
                        pass
                    else:
                        turn_ctx.last_apply_result_ref[0] = (
                            AgentApplyWorkflowEditsResult(
                                attempted=True,
                                apply_result=parsed_inner_result,
                                edits_summary="",
                            )
                        )
                else:
                    turn_ctx.last_apply_result_ref[0] = parsed_result


            if workflow_errors and turn_ctx.is_current_run(turn_ctx.token):
                err_msg = workflow_errors[0][1][:150] if workflow_errors else ""
                if len(workflow_errors) > 1:
                    err_msg += f" (+{len(workflow_errors) - 1} more)"
                if user_message_missing:
                    await turn_ctx.toast(
                        "Your message didn't reach the model. Please try again."
                    )
                else:
                    await turn_ctx.toast(f"Workflow error: {err_msg}")

        # Append agent message as soon as we have content so it always appears
        content_for_display = result.get("content_for_display")

        display_content = (
            content_for_display
            if isinstance(content_for_display, str) and content_for_display
            else content
        )

        display_content += formulas_calc_display_appendix(response)

        meta = {
            "turn_id": turn_ctx.turn_id,
            "agent": turn_ctx.agent_display,
            "source": "agent_response",
            "workflow_response": {
                "reply": display_content,
                "result_kind": result.get("kind"),
            },
            "parsed_edits": result.get("edits", []),
            "apply": apply_meta_with_formulas_calc_tool_status(
                response,
                result.get("apply_result", {}),
            ),
        }

        if result.get("kind") == "parse_error":
            meta["format_error"] = True
        if follow_up_contexts_this_turn:
            meta["follow_up_contexts"] = follow_up_contexts_this_turn
        turn_ctx.append_message("agent", display_content, meta=meta)

        if not turn_ctx.is_current_run(turn_ctx.token):
            return
        turn_ctx.set_inline_status(None)

        apply_fn = (
            turn_ctx.apply_from_agent
            if turn_ctx.apply_from_agent
            else turn_ctx.set_graph
        )
        if result.get("kind") == "applied" and result.get("graph") is not None:
            raw_graph = result["graph"]
            _client_todo_supplements: list[str] = []

            try:
                if isinstance(raw_graph, ProcessGraph):
                    graph_to_apply = raw_graph

                elif isinstance(raw_graph, dict):
                    graph_to_apply = ProcessGraph.model_validate(raw_graph)

                elif isinstance(raw_graph, ModelDumpable):
                    graph_to_apply = ProcessGraph.model_validate(
                        raw_graph.model_dump(by_alias=True)
                    )

                else:
                    raise TypeError(
                        "expected ProcessGraph, dict, or model with model_dump"
                    )

            except (TypeError, ValidationError) as exc:
                raise ValueError(
                    f"ValidateGraphToApply: invalid graph: {exc}"
                ) from exc


            # Client-side todos: code-block task only if coding_is_allowed;
            # import review always when applicable.
            from agents.chat.context.todo_list_manager import (
                augment_graph_with_client_tasks,
            )

            parser_output = response.merged_response.parser_output

            parsed_actions = (
                parser_output.actions
                if parser_output is not None
                else ParsedActions()
            )

            graph_to_apply, extra_supp = await augment_graph_with_client_tasks(
                graph_to_apply,
                parsed_actions.edits,
                coding_is_allowed=turn_ctx.coding_is_allowed,
            )

            _client_todo_supplements.extend(extra_supp)

            # Validate via ValidateGraphToApply; canvas expects ProcessGraph.
            applied_ok = False

            if isinstance(graph_to_apply, dict):
                vg, v_err = await validate_graph_to_apply_inline(graph_to_apply)

                if v_err or vg is None:
                    graph_to_apply = None

                    if turn_ctx.is_current_run(turn_ctx.token):
                        await turn_ctx.toast(
                            f"Could not validate graph: {(v_err or '')[:120]}",
                        )
                else:
                    graph_to_apply = vg

            if isinstance(graph_to_apply, ProcessGraph):
                apply_fn(graph_to_apply)

                prev_apply: AgentApplyWorkflowEditsResult = (
                    turn_ctx.last_apply_result_ref[0]
                )

                refreshed_result = await refresh_last_graph_apply_result(
                    prev_apply,
                    ApplyWorkflowEditsResult(
                        success=True,
                        graph=graph_to_apply,
                        error=None,
                    ),
                    supplement_summary="; ".join(_client_todo_supplements),
                )

                turn_ctx.last_apply_result_ref[0] = refreshed_result

                await turn_ctx.toast("Applied")
                applied_ok = True

            if applied_ok:
                parser_output = response.merged_response.parser_output

                parsed_actions = (
                    parser_output.actions
                    if parser_output is not None
                    else ParsedActions()
                )

                edits = parsed_actions.edits

                had_import_workflow = any(
                    edit.action == IMPORT_WORKFLOW_ACTION
                    for edit in edits
                )

                had_todo = any(
                    edit.action in TODO_ACTIONS
                    for edit in edits
                )

                had_add_comment = any(
                    edit.action == ADD_COMMENT_ACTION
                    for edit in edits
                )

                content_holder = [content]
                post_ctx = PostApplyFollowUpContext(
                    graph_ref=turn_ctx.graph_ref,
                    state=turn_ctx.state,
                    token=turn_ctx.token,
                    turn_id=turn_ctx.turn_id,
                    agent_role_id=turn_ctx.profile,
                    agent_label=turn_ctx.agent_display,
                    max_rounds=max_wd_follow_ups,
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
                    replace_agent_message_row=turn_ctx.replace_agent_message_row,
                    stream_buffer_ref=turn_ctx.stream_buffer_ref,
                    agent_workflow_path=_WORKFLOW_DESIGNER_WORKFLOW_PATH,
                    apply_fn=apply_fn,
                    record_llm_prompt_view=turn_ctx.record_llm_prompt_view,
                )
                await run_post_apply_follow_up_rounds_async(
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
            # Ensure last_apply_result is stored so the next turn and any
            # same-turn retry receive a valid self-correction block.
            failed_apply_value = (
                result.get("last_apply_result")
                or result.get("apply_result")
            )

            failed_apply = normalize_last_apply_result(failed_apply_value)

            if failed_apply is not None:
                turn_ctx.last_apply_result_ref[0] = failed_apply
                err_str = failed_apply.error or "Unknown"
            else:
                err_str = "Unknown"

            await turn_ctx.toast(
                f"Could not apply edits: {err_str[:120]}",
            )

            # Same-turn self-correction: workflow_inputs.build_self_correction_retry_inputs; we run and apply/toast
            if turn_ctx.is_current_run(turn_ctx.token):
                turn_ctx.set_inline_status("Retrying with error context…")
                try:
                    _graph = turn_ctx.graph_ref[0]
                    _previous_turn = await format_previous_turn(turn_ctx.state.history)
                    retry_inputs = build_self_correction_retry_inputs(
                        turn_ctx.last_apply_result_ref[0],
                        _graph,
                        turn_ctx.get_recent_changes()
                        if turn_ctx.get_recent_changes
                        else None,
                        runtime=await get_runtime_for_prompts(_graph),
                        coding_is_allowed=turn_ctx.coding_is_allowed,
                        contribution_is_allowed=turn_ctx.contribution_is_allowed,
                        previous_turn=_previous_turn,
                        language_hint=wf_lang_cell[0],
                        session_language=turn_ctx.state.session_language,
                    )
                    turn_ctx.prepare_stream_row()
                    retry_response = await turn_ctx.run_workflow_streaming(
                        run_agent_workflow,
                        retry_inputs,
                        overrides,
                        _WORKFLOW_EXECUTION_TIMEOUT,
                        _run_token=turn_ctx.token,
                        workflow_path=_WORKFLOW_DESIGNER_WORKFLOW_PATH,
                    )

                    record_llm_prompt_view_if_present(
                        retry_response,
                        turn_ctx.record_llm_prompt_view,
                    )

                    _ = maybe_pin_session_language_from_workflow_response(
                        turn_ctx.state,
                        retry_response,
                    )

                    retry_merged = retry_response.merged_response
                    retry_result = retry_merged.result
                    if not turn_ctx.is_current_run(turn_ctx.token):
                        return
                    r_result = retry_result
                    raw_edits = r_result.get("edits")

                    try:
                        retry_edits = MultipleEditsSequential.model_validate(
                            {"edits": raw_edits if raw_edits is not None else []}
                        ).edits
                    except ValidationError:
                        retry_edits = []

                    await set_commenter_for_new_comments(
                        retry_edits,
                        agent_role_id=turn_ctx.profile,
                    )


                    r_kind = r_result.get("kind")

                    if r_kind == "applied":
                        raw_graph = r_result.get("graph")

                        try:
                            process_graph = ProcessGraph.model_validate(raw_graph)
                        except ValidationError as exc:
                            graph_to_apply = None
                            validation_error = str(exc)

                            if turn_ctx.is_current_run(turn_ctx.token):
                                await turn_ctx.toast(
                                    f"Retry graph validation failed: {validation_error[:100]}",
                                )
                        else:
                            vg, v_err = await validate_graph_to_apply_inline(
                                process_graph,
                            )

                            if v_err or vg is None:
                                graph_to_apply = None

                                if turn_ctx.is_current_run(turn_ctx.token):
                                    await turn_ctx.toast(
                                        f"Retry graph validation failed: {(v_err or '')[:100]}",
                                    )
                            else:
                                graph_to_apply = vg

                                from agents.chat.context.todo_list_manager import (
                                    augment_graph_with_client_tasks,
                                )

                                graph_to_apply, _retry_supp = (
                                    await augment_graph_with_client_tasks(
                                        graph_to_apply,
                                        retry_edits,
                                        coding_is_allowed=turn_ctx.coding_is_allowed,
                                    )
                                )

                        if isinstance(graph_to_apply, ProcessGraph):
                            apply_fn(graph_to_apply)

                            await turn_ctx.toast("Applied (after retry)")

                            retry_reply = (retry_merged.reply or "").strip()
                            if retry_reply:
                                content = content + "\n\n" + retry_reply
                                result["content_for_display"] = content

                                turn_ctx.append_message(
                                    "agent",
                                    retry_reply,
                                    meta={
                                        "turn_id": turn_ctx.turn_id,
                                        "agent": turn_ctx.agent_display,
                                        "source": "agent_response",
                                        "workflow_response": {
                                            "reply": retry_reply,
                                            "result_kind": "applied",
                                        },
                                    },
                                )

                            retry_apply = normalize_last_apply_result(
                                r_result.get("last_apply_result")
                                or r_result.get("apply_result")
                            )

                            if retry_apply is not None:
                                turn_ctx.last_apply_result_ref[0] = retry_apply

                    elif r_kind == "apply_failed":
                        failed_apply_value = (
                            r_result.get("last_apply_result")
                            or r_result.get("apply_result")
                        )

                        failed_apply = normalize_last_apply_result(
                            failed_apply_value
                        )

                        if failed_apply is not None:
                            turn_ctx.last_apply_result_ref[0] = failed_apply
                            retry_error = failed_apply.error or "Unknown"
                        else:
                            retry_error = "Unknown"

                        await turn_ctx.toast(
                            f"Retry also failed: {retry_error[:80]}"
                        )

                except (TypeError, WorkflowTimeoutError):
                    pass
                turn_ctx.set_inline_status(None)
        finalize_workflow_designer_turn_session_language(
            turn_ctx.state, response, debug_log=turn_ctx.workflow_debug_log
        )
        turn_ctx.persist_history_debounced()
        return
