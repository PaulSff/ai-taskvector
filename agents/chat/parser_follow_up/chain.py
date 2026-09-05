"""
Parser-output tool follow-up chain and post-apply review rounds for agents chat.

Orchestrates tool follow-ups in catalog order (registered tool runners), then re-runs
``agent_workflow``; optional post-apply rounds (import / todo / comment).
"""

from __future__ import annotations

import asyncio
import inspect
import time
from copy import deepcopy
from dataclasses import replace
from typing import Any

import agents.follow_ups as agents_follow_ups
from agents.chat.agent_workflow import (
    refresh_last_graph_apply_result,
    run_agent_workflow,
)
from agents.chat.agent_workflow.wf_response_schema import (
    AgentWorkflowResponse,
)
from agents.chat.context.context_mergers import (
    merge_preserved_apply_failure_into_response,
)
from agents.chat.context.context_signals import (
    workflow_merge_response_apply_failed,
    workflow_response_is_question,
)
from agents.chat.context.follow_up_context import (
    ExecutionFollowUpContext,
    ParserChainRunner,
    PostExecutionFollowUpContext,
    WDFollowUpAcc,
)
from agents.chat.context.language_control import (
    maybe_pin_session_language_from_workflow_response,
)
from agents.chat.context.llm_prompt_inspector import record_llm_prompt_view_if_present
from agents.chat.context.todo_list_manager import get_summary_params
from agents.chat.utils.workflow_output_normalizer import (
    formulas_calc_display_appendix,
)
from agents.follow_ups import DEFAULT_FOLLOW_UP_USER_MESSAGE
from agents.prompts import (
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE,
)
from agents.roles.workflow_designer.workflow_inputs import (
    build_agent_workflow_initial_inputs,
    default_wf_language_hint,
)
from agents.tools.calendar.follow_ups import CALENDAR_FOLLOW_UP_USER_MESSAGE
from agents.tools.clone_role.follow_ups import CLONE_ROLE_FOLLOW_UP_USER_MESSAGE
from agents.tools.follow_up_common import TOOL_EMPTY_USER_MESSAGE
from agents.tools.formulas_calc.follow_ups import (
    FORMULAS_CALC_FOLLOW_UP_USER_MESSAGE,
)
from agents.tools.list_dir.follow_ups import LIST_DIR_FOLLOW_UP_USER_MESSAGE
from agents.tools.read_code_block.follow_ups import (
    READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE,
)
from agents.tools.read_file.follow_ups import (
    REQUEST_FILE_CONTENT_FOLLOW_UP_USER_MESSAGE,
)
from agents.tools.report.follow_ups import REPORT_FOLLOW_UP_USER_MESSAGE
from core.schemas import ProcessGraph
from core.schemas.primitives import Data
from gui.components.settings import get_coding_is_allowed, get_contribution_is_allowed

from .tool_follow_ups_runner import run_role_ordered_follow_ups

# ─────────────────────────────────────────────────────────────────────────────────
#  PHASE 1: Execution follow_up rounds
# ─────────────────────────────────────────────────────────────────────────────────

async def run_execute_follow_up_chain_async(
    ctx: ExecutionFollowUpContext,
    resp: AgentWorkflowResponse,
) -> AgentWorkflowResponse | None:
    """
    Async version: If parser_output requests tools, fetch context and re-run
    agent_workflow.

    Returns None when the user cancelled the run mid-chain.
    """

    def _hint() -> str:
        return ctx.wf_language_hint[0]

    async def _checkpoint(name: str) -> None:
        print(
            f"[parser_follow_up_chain] "
            f"checkpoint: {name} ts={time.time():.3f}"
        )

    _ = maybe_pin_session_language_from_workflow_response(
        ctx.state,
        resp,
    )

    ctx.wf_language_hint[0] = default_wf_language_hint(
        ctx.state.session_language
    )

    preserved_apply_failure: AgentWorkflowResponse | None = None

    def get_apply_failure(
        response_to_check: AgentWorkflowResponse,
    ) -> AgentWorkflowResponse | None:
        if not workflow_merge_response_apply_failed(
            response_to_check
        ):
            return None

        merge_response = response_to_check.merged_response

        return replace(
            response_to_check,
            merged_response=replace(
                merge_response,
                result=deepcopy(merge_response.result),
                status=deepcopy(merge_response.status),
                workflow_errors=deepcopy(
                    merge_response.workflow_errors
                ),
            ),
        )

    response: AgentWorkflowResponse = resp

    record_llm_prompt_view_if_present(
        response,
        ctx.record_llm_prompt_view,
    )

    preserved_apply_failure = get_apply_failure(response)

    await _checkpoint("after_primer")

    if workflow_response_is_question(response):
        await _checkpoint("return_question_no_chain")
        return response

    for i in range(ctx.max_rounds):
        await _checkpoint(f"loop_start:{i}")

        po = response.merged_response.parser_output

        if po is None:
            raise ValueError(
                "Expected parser_output before running "
                "follow-up handlers"
            )

        purple = "\033[94m"
        reset = "\033[0m"

        msg = (
            "[parser_follow_up_chain] LLM tool call: "
            "po type="
            + type(po).__name__
            + " keys="
            + (
                str(list(po.keys()))
                if isinstance(po, dict)
                else "None"
            )
        )

        print(f"{purple}{msg}{reset}", flush=True)

        grey = "\033[38;5;245m"

        print(
            f"{grey}[parser_follow_up_chain] "
            f"po={po!r}{reset}",
            flush=True,
        )

        acc = WDFollowUpAcc()

        ctx.follow_up_source_response = response

        await _checkpoint(
            f"before_ordered_followups:{i}"
        )

        await run_role_ordered_follow_ups(
            ctx,
            po,
            response,
            _hint,
            acc,
        )

        await _checkpoint(
            f"after_ordered_followups:{i}"
        )

        context_chunks = acc.context_chunks
        any_empty_tool = acc.any_empty_tool
        read_code_ids_for_msg = acc.read_code_ids_for_msg
        implementation_links_for_types = (
            acc.implementation_links_for_types
        )
        report_follow_up = acc.report_follow_up
        formulas_calc_follow_up = (
            acc.formulas_calc_follow_up
        )
        calendar_follow_up = acc.calendar_follow_up
        clone_role_follow_up = acc.clone_role_follow_up
        list_dir_follow_up = acc.list_dir_follow_up
        read_file_follow_up = acc.read_file_follow_up

        follow_up_context: str | None = None

        if context_chunks:
            follow_up_context = "\n\n---\n\n".join(
                context_chunks
            )

        follow_up_messages: list[str] = []

        if read_code_ids_for_msg:
            follow_up_messages.append(
                READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE.format(
                    unit_ids=", ".join(
                        str(x) for x in read_code_ids_for_msg
                    ),
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if report_follow_up:
            follow_up_messages.append(
                REPORT_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if any_empty_tool:
            follow_up_messages.append(
                TOOL_EMPTY_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if formulas_calc_follow_up:
            follow_up_messages.append(
                FORMULAS_CALC_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if calendar_follow_up:
            follow_up_messages.append(
                CALENDAR_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if clone_role_follow_up:
            follow_up_messages.append(
                CLONE_ROLE_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if list_dir_follow_up:
            follow_up_messages.append(
                LIST_DIR_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if read_file_follow_up:
            follow_up_messages.append(
                REQUEST_FILE_CONTENT_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if follow_up_messages:
            follow_up_msg = "\n\n".join(
                follow_up_messages
            )
        else:
            follow_up_msg = (
                DEFAULT_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )


        if not follow_up_context:
            await _checkpoint(
                f"break_no_follow_up_context:{i}"
            )
            break

        ctx.follow_up_contexts.append(follow_up_context)

        await _checkpoint(
            f"appended_follow_up_context:{i}"
        )

        if not ctx.is_current_run(ctx.token):
            await _checkpoint(
                f"return_none_cancelled_pre_llm:{i}"
            )
            return None

        prev_content = (
            response.merged_response.reply or ""
        ).strip()

        if prev_content:
            prev_show = (
                prev_content
                + formulas_calc_display_appendix(response)
            )

            ctx.append_message(
                "agent",
                prev_show,
                meta={
                    "turn_id": ctx.turn_id,
                    "agent": ctx.agent_label,
                    "source": "agent_response",
                    "workflow_response": {
                        "reply": prev_show,
                    },
                },
            )

        ctx.prepare_stream_row()

        follow_up_msg = (
            ctx.normalize_user_message_for_workflow(
                follow_up_msg
            )
        )

        graph_ref = ctx.graph_ref[0]

        runtime = await ctx.get_runtime_for_prompts(
            graph_ref
        )

        previous_turn = await ctx.format_previous_turn(
            ctx.state.history
        )

        initial_inputs = (
            build_agent_workflow_initial_inputs(
                follow_up_msg,
                graph_ref,
                ctx.last_apply_result_ref[0],
                (
                    ctx.get_recent_changes()
                    if ctx.get_recent_changes
                    else None
                ),
                follow_up_context,
                runtime=runtime,
                coding_is_allowed=(
                    get_coding_is_allowed()
                ),
                contribution_is_allowed=(
                    get_contribution_is_allowed()
                ),
                previous_turn=previous_turn,
                language_hint=_hint(),
                session_language=(
                    ctx.state.session_language
                ),
                analyst_mode=ctx.analyst_mode,
            )
        )

        if ctx.extend_agent_initial_inputs_async is not None:
            await _checkpoint(
                f"before_extend_initial_inputs:{i}"
            )

            initial_inputs = (
                await ctx.extend_agent_initial_inputs_async(
                    initial_inputs
                )
            )

            await _checkpoint(
                f"after_extend_initial_inputs:{i}"
            )

        graph = ctx.graph_ref[0]

        graph_summary = get_summary_params(
            get_coding_is_allowed(),
            graph,
        )

        units_library_base = dict(
            ctx.overrides.get("units_library") or {}
        )

        if implementation_links_for_types:
            units_library = {
                **units_library_base,
                "implementation_links_for_types": list(
                    dict.fromkeys(
                        implementation_links_for_types
                    )
                ),
            }
        else:
            units_library = {
                key: value
                for key, value in units_library_base.items()
                if key != "implementation_links_for_types"
            }

        if ctx.analyst_mode:
            graph_summary = dict(
                ctx.overrides.get("graph_summary") or {}
            )

            graph_summary.setdefault(
                "include_structure",
                False,
            )

            graph_summary.setdefault(
                "include_code_block_source",
                False,
            )
        else:
            graph: ProcessGraph | None

            graph = ctx.graph_ref[0]

            graph_summary = get_summary_params(
                get_coding_is_allowed(),
                graph,
            )

        follow_up_overrides = {
            **ctx.overrides,
            "graph_summary": graph_summary,
            "rag_search": {
                **(
                    ctx.overrides.get("rag_search")
                    or {}
                ),
                "ignore": True,
            },
            "units_library": units_library,
        }

        await _checkpoint(
            f"before_run_workflow_streaming:{i}"
        )

        # run workflow streaming and invoke the callback
        previous_graph = ctx.graph_ref[0]

        if ctx.agent_workflow_path is None:
            response = await ctx.run_workflow_streaming(
                run_agent_workflow,
                initial_inputs,
                follow_up_overrides,
                None,
                _run_token=ctx.token,
            )
        else:
            response = await ctx.run_workflow_streaming(
                run_agent_workflow,
                initial_inputs,
                follow_up_overrides,
                None,
                _run_token=ctx.token,
                workflow_path=ctx.agent_workflow_path,
            )

        if ctx.on_workflow_response is not None:
            await ctx.on_workflow_response(
                response,
                previous_graph,
            )

        await _checkpoint(
            f"after_run_workflow_streaming:{i}"
        )

        record_llm_prompt_view_if_present(
            response,
            ctx.record_llm_prompt_view,
        )

        _ = maybe_pin_session_language_from_workflow_response(
            ctx.state,
            response,
        )

        ctx.wf_language_hint[0] = (
            default_wf_language_hint(
                ctx.state.session_language
            )
        )

        if workflow_response_is_question(response):
            await _checkpoint(
                f"break_question_after_stream:{i}"
            )
            break

        new_apply_failure = get_apply_failure(response)

        if new_apply_failure is not None:
            preserved_apply_failure = new_apply_failure

        if not ctx.is_current_run(ctx.token):
            await _checkpoint(
                f"return_none_cancelled_post_llm:{i}"
            )
            return None

        await _checkpoint(
            f"end_round_no_question:{i}"
        )

    await _checkpoint(
        "exit_after_rounds_or_break"
    )

    if (
        preserved_apply_failure is not None
        and response.merged_response.result.get("kind")
        != "applied"
    ):
        response = merge_preserved_apply_failure_into_response(
            response,
            preserved_apply_failure,
        )

    await _checkpoint(
        "return_final_response"
    )

    return response



# ─────────────────────────────────────────────────────────────────────────────────
#  PHASE 2: Post-execution follow-up rounds
# ─────────────────────────────────────────────────────────────────────────────────


async def run_post_execution_follow_up_chain_async(
    ctx: PostExecutionFollowUpContext,
    *,
    result: Data,
    content_holder: list[str],
    parser_chain_runner: ParserChainRunner,
    # flags: PostExecuteFlags,
) -> None:
    """After a successful canvas apply, run optional review agent rounds (import / todo / …)."""
    from agents.chat.context.todo_list_manager import graph_has_any_open_tasks

    def _hint() -> str:
        return ctx.wf_language_hint[0]

    async def _checkpoint(name: str) -> None:
        print(
            f"[post_apply_follow_up_rounds] checkpoint: {name} ts={time.time():.3f}",
            flush=True,
        )

    def _post_apply_messages(round_idx: int) -> tuple[str, str] | None:
        if round_idx == 0:
            if flags.had_import_workflow:
                return (
                    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                )
            if flags.had_add_comment and flags.had_todo:
                return (
                    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                )
            if flags.had_add_comment:
                return (
                    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                )
            if flags.had_todo:
                return (
                    WORKFLOW_DESIGNER_TODO_FOLLOW_UP.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                )
            return (
                agents_follow_ups.DEFAULT_POST_APPLY_FOLLOW_UP_INJECT.format(
                    language=_hint(),
                    session_language=_hint(),
                ),
                agents_follow_ups.DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                ),
            )
        if not graph_has_any_open_tasks(ctx.graph_ref[0]):
            return None
        return (
            WORKFLOW_DESIGNER_TODO_FOLLOW_UP.format(
                language=_hint(),
                session_language=_hint(),
            ),
            WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE.format(
                language=_hint(),
                session_language=_hint(),
            ),
        )

    content = content_holder[0]
    await _checkpoint("start")
    for post_round in range(ctx.max_rounds):
        await _checkpoint(f"loop_start:{post_round}")

        try:
            pair = _post_apply_messages(post_round)

            # print("[phase2] DEBUG post_round", post_round, "pair=", pair, flush=True)

            await _checkpoint(
                f"after_pick_messages:{post_round}:{'None' if pair is None else 'pair'}"
            )
            if pair is None:
                await _checkpoint(f"break_no_pair:{post_round}")
                break
            post_msg, post_user_msg = pair

            if not ctx.is_current_run(ctx.token):
                await _checkpoint(f"break_not_current_run:{post_round}")
                break

            ctx.set_inline_status("Reviewing…")
            await _checkpoint(f"set_inline_status:{post_round}")

            try:
                ctx.prepare_stream_row()
                await _checkpoint(f"prepared_stream_row:{post_round}")

                post_user_msg = ctx.normalize_user_message_for_workflow(post_user_msg)

                # print("[phase2] DEBUG post_msg =", post_msg, flush=True)
                # print("[phase2] DEBUG post_user_msg(normalized) =", post_user_msg, flush=True)

                await _checkpoint(f"normalized_user_msg:{post_round}")

                _graph = ctx.graph_ref[0]
                await _checkpoint(f"read_graph_ref:{post_round}:{_graph is not None}")

                _gd_post = (
                    _graph.model_dump(by_alias=True)
                    if _graph is not None and hasattr(_graph, "model_dump")
                    else (_graph if isinstance(_graph, dict) else None)
                )
                await _checkpoint(
                    f"computed_graph_dump:{post_round}:{isinstance(_gd_post, dict)}"
                )

                if isinstance(_gd_post, dict):
                    post_graph = ProcessGraph.model_validate(_gd_post)

                    if ctx.analyst_mode:
                        gs = dict(ctx.overrides.get("graph_summary") or {})
                        gs.setdefault("include_structure", False)
                        gs.setdefault("include_code_block_source", False)
                        ctx.overrides["graph_summary"] = gs

                        await _checkpoint(
                            f"analyst_mode_graph_summary_set:{post_round}"
                        )
                    else:
                        ctx.overrides["graph_summary"] = get_summary_params(
                            get_coding_is_allowed(),
                            post_graph,
                        )

                        await _checkpoint(f"graph_summary_set:{post_round}")


                _runtime = await ctx.get_runtime_for_prompts(_graph)
                await _checkpoint(
                    f"runtime_for_prompts:{post_round}:{_runtime is not None}"
                )
                _previous_turn = await ctx.format_previous_turn(ctx.state.history)
                last_apply = ctx.last_apply_result_ref[0]

                if asyncio.iscoroutine(last_apply):
                    last_apply = await last_apply

                post_inputs = build_agent_workflow_initial_inputs(
                    post_user_msg,
                    _graph,
                    last_apply if isinstance(last_apply, dict) else None,
                    ctx.get_recent_changes() if ctx.get_recent_changes else None,
                    post_msg,
                    runtime=_runtime,
                    coding_is_allowed=get_coding_is_allowed(),
                    contribution_is_allowed=get_contribution_is_allowed(),
                    previous_turn=_previous_turn,
                    language_hint=_hint(),
                    session_language=ctx.state.session_language,
                    analyst_mode=ctx.analyst_mode,
                )
                await _checkpoint(f"built_post_inputs:{post_round}")

                post_stream_kw: dict[str, Any] = {"_run_token": ctx.token}
                if ctx.agent_workflow_path is not None:
                    post_stream_kw["workflow_path"] = ctx.agent_workflow_path
                    await _checkpoint(f"using_agent_workflow_path:{post_round}")
                else:
                    await _checkpoint(f"no_agent_workflow_path:{post_round}")

                await _checkpoint(f"before_run_workflow_streaming:{post_round}")
                post_response = await ctx.run_workflow_streaming(
                    run_agent_workflow,
                    post_inputs,
                    ctx.overrides,
                    None,
                    **post_stream_kw,
                )
                await _checkpoint(f"after_run_workflow_streaming:{post_round}")

                await _checkpoint(f"before_parser_chain:{post_round}")
                post_chained = await parser_chain_runner(post_response)
                await _checkpoint(f"after_parser_chain:{post_round}:{post_chained is None}")

                if post_chained is None:
                    await _checkpoint(f"break_none_from_parser_chain:{post_round}")
                    break
                post_response = post_chained

                # breack if no_edit action is detected
                post_kind = (post_response.get("result") or {}).get("kind")
                if post_kind in ("no_edits", "no_edit"):
                    await _checkpoint(f"break_no_edits_kind:{post_round}")
                    break

                # stop if parser chain emitted structured no_edit (LLM emitted a valid no_edit action)
                post_no_edit = post_response.get("no_edit")
                if isinstance(post_no_edit, dict) and post_no_edit.get("action") == "no_edit":
                    await _checkpoint(f"break_no_edit_action:{post_round}")
                    break

                record_llm_prompt_view_if_present(post_response, ctx.record_llm_prompt_view)
                await _checkpoint(f"recorded_prompt_view:{post_round}")

                post_raw = post_response.get("reply")

                if isinstance(post_raw, dict) and "action" in post_raw:
                    post_raw = post_raw.get("action") or ""
                    await _checkpoint(f"extracted_action_from_reply:{post_round}")

                # break the loop if no_edit action is detected from llm reply
                if isinstance(post_raw, str) and post_raw.strip() == "no_edit":
                    await _checkpoint(f"break_no_edit_action_fallback:{post_round}")
                    break

                post_reply = (
                    post_raw if isinstance(post_raw, str) else str(post_raw or "")
                ).strip()

                if not post_reply and ctx.stream_buffer_ref[0]:
                    post_reply = (ctx.stream_buffer_ref[0] or "").strip()
                    await _checkpoint(f"used_stream_buffer_fallback:{post_round}")

                await _checkpoint(f"computed_post_reply_len:{post_round}:{len(post_reply)}")

                if post_reply:
                    content = content + "\n\n" + post_reply
                    content_holder[0] = content
                    result["content_for_display"] = content
                    await _checkpoint(f"appended_post_reply:{post_round}:{len(content)}")

                    last = ctx.state.history[-1] if ctx.state.history else None
                    await _checkpoint(
                        f"history_last_present:{post_round}:{isinstance(last, dict)}"
                    )

                    if (
                        isinstance(last, dict)
                        and last.get("role") == "agent"
                        and last.get("turn_id") == ctx.turn_id
                    ):
                        last["content"] = content
                        wr = last.get("workflow_response")
                        if isinstance(wr, dict):
                            wr["reply"] = content
                        else:
                            last["workflow_response"] = {"reply": content}
                        ctx.replace_agent_message_row(last)
                        await _checkpoint(f"replaced_agent_row:{post_round}")
                    else:
                        ctx.append_message(
                            "agent",
                            post_reply,
                            meta={
                                "turn_id": ctx.turn_id,
                                "agent": ctx.agent_label,
                                "source": "agent_response_post_apply",
                                "workflow_response": {
                                    "reply": post_reply,
                                    "result_kind": "post_apply",
                                    "post_apply_round": post_round,
                                },
                            },
                        )
                        await _checkpoint(f"appended_agent_message:{post_round}")

                await _checkpoint(f"before_workflow_response_question_check:{post_round}")

                # break the loop if the llm has just asked a question
                if workflow_response_is_question(post_response):
                    await _checkpoint(f"break_question_stop_auto_rounds:{post_round}")
                    break

                pw = post_response.get("result") or {}
                post_kind = pw.get("kind")
                post_graph = pw.get("graph")
                await _checkpoint(
                    f"post_result_fields:{post_round}:kind={post_kind}:{post_graph is not None}"
                )

                synced_post_graph = False
                if (
                    post_kind == "applied"
                    and post_graph is not None
                    and ctx.is_current_run(ctx.token)
                ):
                    await _checkpoint(f"attempt_canvas_sync:{post_round}")
                    try:
                        if isinstance(post_graph, dict):
                            from agents.chat.agent_workflow.helpers import (
                                validate_graph_to_apply_inline,
                            )
                            from agents.chat.context.todo_list_manager import (
                                augment_graph_with_client_tasks,
                            )
                            from agents.chat.role_turns.turn_edits import (
                                set_commenter_for_new_comments,
                            )

                            _post_edits = pw.get("edits") or []
                            await _checkpoint(
                                f"set_commenter_for_new_comments:{post_round}:{len(_post_edits)}"
                            )
                            await set_commenter_for_new_comments(
                                _post_edits, agent_role_id=ctx.agent_role_id
                            )


                            if isinstance(post_graph, dict):
                                post_graph = ProcessGraph.model_validate(post_graph)

                            post_graph, _post_supp = await augment_graph_with_client_tasks(
                                post_graph,
                                _post_edits,
                                coding_is_allowed=get_coding_is_allowed(),
                            )

                            await _checkpoint(
                                f"augment_graph_with_client_tasks:{post_round}"
                            )
                            post_pg, _p_err = await validate_graph_to_apply_inline(
                                post_graph
                            )
                            await _checkpoint(
                                f"validated_graph_to_apply_for_canvas:{post_round}:{post_pg is not None}"
                            )
                        else:
                            post_pg = post_graph
                            await _checkpoint(f"post_graph_not_dict:{post_round}")

                        if post_pg is not None:
                            ctx.apply_fn(post_pg)
                            await _checkpoint(f"applied_post_graph:{post_round}")

                            prev_apply = ctx.last_apply_result_ref[0]
                            if asyncio.iscoroutine(prev_apply):
                                prev_apply = await prev_apply

                            ctx.last_apply_result_ref[
                                0
                            ] = await refresh_last_graph_apply_result(
                                prev_apply,
                                ctx.graph_ref[0],
                                supplement_summary="",
                            )

                            synced_post_graph = True
                            await _checkpoint(f"refreshed_last_apply_result:{post_round}")
                        else:
                            await _checkpoint(f"post_pg_is_none_no_apply:{post_round}")
                    except (KeyError, TypeError, IndexError):
                        await _checkpoint(f"canvas_sync_exception:{post_round}")

                if not synced_post_graph and pw.get("last_apply_result"):
                    ap = pw["last_apply_result"]
                    ctx.last_apply_result_ref[0] = (
                        ap if isinstance(ap, dict) and not inspect.isawaitable(ap) else {}
                    )
                    await _checkpoint(f"synced_last_apply_result_from_agent:{post_round}")

                post_errors = post_response.get("workflow_errors") or []
                await _checkpoint(
                    f"workflow_errors:{post_round}:{len(post_errors) if isinstance(post_errors, list) else 'na'}"
                )
                if post_errors and ctx.is_current_run(ctx.token):
                    await _checkpoint(f"toast_workflow_error:{post_round}")
                    await ctx.toast(f"Workflow error: {post_errors[0][1][:120]}")
                    await _checkpoint(f"toast_sent:{post_round}")

            except (KeyError, TypeError, IndexError):
                await _checkpoint(f"round_exception:{post_round}")

        finally:
            ctx.set_inline_status(None)
            await _checkpoint(f"clear_inline_status:{post_round}")

    await _checkpoint("end")
