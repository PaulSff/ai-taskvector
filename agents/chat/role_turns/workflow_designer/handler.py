"""Workflow Designer agents chat turn (extracted from ``chat.py``).
previous_graph = turn_ctx.graph_ref[0]

workflow response
    ├─ runtime applies workflow edits inline
    ├─ graph_ref now contains after_graph
    ├─ collect parser edits
    ├─ collect parser tool_actions
    ├─ validate after_graph
    ├─ augment client-side tasks
    ├─ apply only changed client-side supplements
    └─ refresh last_apply_result_ref

optional final planning response
    └─ repeat the same response reconciliation

persist final state

---
The parser runner must invoke the callback for every response it creates:

previous_graph = context.graph_ref[0]

response = await context.run_workflow_streaming(
    run_agent_workflow,
    inputs,
    context.overrides,
    timeout,
    _run_token=context.token,
    workflow_path=context.agent_workflow_path,
)

if context.on_workflow_response is not None:
    await context.on_workflow_response(
        response,
        previous_graph,
    )
The retry path should likewise call run_workflow_turn(retry_inputs) rather than parsing and applying retry_response["graph"] itself:
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from agents.chat.agent_workflow import (
    AgentWorkflowResponse,
    MergeResponse,
    build_agent_workflow_unit_param_overrides,
    get_runtime_for_prompts,
    refresh_last_graph_apply_result,
    run_agent_workflow,
)
from agents.chat.agent_workflow.helpers import (
    get_optional_str,
    validate_graph_to_apply_inline,
)
from agents.chat.agent_workflow.wf_response_schema import is_apply_result
from agents.chat.context import PostExecutionFollowUpContext
from agents.chat.context.follow_up_context import (
    ExecutionFollowUpContext,
    PostEditFlags,
)
from agents.chat.context.language_control import (
    finalize_workflow_designer_turn_session_language,
)
from agents.chat.context.todo_list_manager import get_summary_params
from agents.chat.context.todo_list_manager.todo_list_manager import (
    augment_graph_with_client_tasks,
)
from agents.chat.handlers.auto_delegate_turn import try_run_auto_delegate_before_turn
from agents.chat.handlers.chat_turn_context import (
    format_previous_turn,
    normalize_user_message_for_workflow,
)
from agents.chat.parser_follow_up import (
    run_execution_follow_up_chain_async,
    run_post_execution_follow_up_chain_async,
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
    COMMENT_ACTIONS,
    IMPORT_WORKFLOW_ACTION,
    TODO_ACTIONS,
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
)
from core.schemas.primitives import (
    Data,
    ModelDumpable,
    WorkflowInputs,
)
from gui.components.settings import get_workflow_designer_max_follow_ups
from gui.components.settings.paths import UNITS_DIR
from runtime.run import WorkflowTimeoutError
from units.taskvector.agent_orchestrator.utils.batch_update_helpers import (
    ProgressResult,
)

from ..context import RoleChatTurnContext

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


class WorkflowDesignerChatHandler:
    """Runs one Workflow Designer turn."""

    @property
    def role_id(self) -> str:
        return WORKFLOW_DESIGNER_ROLE_ID

    @property
    def role_name(self) -> str:
        return get_role(self.role_id).role_name

    @staticmethod
    def parse_error_result(content: str) -> ProgressResult:
        return ProgressResult(
            kind="parse_error",
            content_for_display=content,
            apply_result=None,
            edits=[],
        )

    @staticmethod
    def get_apply_result(
        status: Data,
        result: ProgressResult,
    ) -> AgentApplyWorkflowEditsResult | None:
        value = (
            status.get("last_apply_result")
            or result.get("last_apply_result")
        )

        if not is_apply_result(value):
            return None

        return value


    async def run_turn(
        self,
        turn_ctx: RoleChatTurnContext,
        *,
        message_for_workflow: str,
    ) -> None:
        response = AgentWorkflowResponse()
        content = ""
        result: ProgressResult = {}

        role_cfg: RoleConfig = get_role(self.role_id)

        overrides: WorkflowInputs = (
            build_agent_workflow_unit_param_overrides(
                provider=role_cfg.provider,
                report_output_dir=str(Path(turn_ctx.mydata_dir) / "reports"),
                model_name=role_cfg.ollama_model,
                host=role_cfg.ollama_host,
                llm_options_role_id=self.role_id,
                rag_top_k_role_id=self.role_id,
            )
        )

        graph = turn_ctx.graph_ref[0]

        validated_graph, validation_error = (
            await validate_graph_to_apply_inline(graph)
        )
        if validation_error is not None:
            raise ValueError(validation_error)

        overrides["graph_summary"] = get_summary_params(
            turn_ctx.coding_is_allowed,
            validated_graph,
        )

        def failed_apply_result(
            error: str,
            *,
            attempted: bool = True,
        ) -> AgentApplyWorkflowEditsResult:
            return AgentApplyWorkflowEditsResult(
                attempted=attempted,
                apply_result=ApplyWorkflowEditsResult(
                    success=False,
                    graph=turn_ctx.graph_ref[0],
                    error=error,
                ),
                edits_summary="No workflow edits were applied.",
            )

        follow_up_contexts_this_turn: list[str] = []
        wf_lang_cell = [
            default_wf_language_hint(turn_ctx.state.session_language)
        ]

        wd_role = get_role(WORKFLOW_DESIGNER_ROLE_ID)
        max_wd_follow_ups = (
            wd_role.follow_up_max_rounds
            if wd_role.follow_up_max_rounds is not None
            else get_workflow_designer_max_follow_ups()
        )

        wd_follow_up_tools = (
            wd_role.tools
            if wd_role.tools
            else tuple(
                tid
                for tid, _ in ordered_tools_for_role_id(
                    WORKFLOW_DESIGNER_ROLE_ID
                )
            )
        )

        # All parser actions emitted during this handler turn are retained.
        turn_actions = ParsedActions()

        had_import_workflow = False
        had_todo = False
        had_add_comment = False


        def collect_actions(
            workflow_response: AgentWorkflowResponse,
        ) -> None:
            nonlocal had_import_workflow
            nonlocal had_todo
            nonlocal had_add_comment

            merged = workflow_response.merged_response

            apply_result_value = (
                merged.status.get("last_apply_result")
                or merged.result.get("last_apply_result")
                or {}
            )

            applied_ok = (
                isinstance(apply_result_value, dict)
                and apply_result_value.get("attempted") is True
                and apply_result_value.get("success") is True
            )

            parser_output = merged.parser_output
            if parser_output is None:
                return

            actions = parser_output.actions

            turn_actions.edits.extend(actions.edits)

            for action, values in actions.tool_actions.items():
                turn_actions.tool_actions.setdefault(action, []).extend(values)

            if not applied_ok:
                return

            had_import_workflow = had_import_workflow or any(
                edit.action == IMPORT_WORKFLOW_ACTION
                for edit in actions.edits
            )

            had_todo = had_todo or any(
                edit.action in TODO_ACTIONS
                for edit in actions.edits
            )

            had_add_comment = had_add_comment or any(
                edit.action in COMMENT_ACTIONS
                for edit in actions.edits
            )

        async def reconcile_workflow_response(
            workflow_response: AgentWorkflowResponse,
            *,
            previous_graph: ProcessGraph,
        ) -> None:
            """
            Reconcile one complete workflow transition.

            The workflow runtime has already applied its graph edits inline.
            This function therefore does not reapply those edits. It only:
              - collects edits and tool actions;
              - validates the runtime's after graph;
              - applies client-side task supplements when needed;
              - refreshes last_apply_result_ref.
            """
            collect_actions(workflow_response)

            after_graph = turn_ctx.graph_ref[0]

            validated_after_graph, graph_error = (
                await validate_graph_to_apply_inline(after_graph)
            )

            if graph_error is not None or validated_after_graph is None:
                raise ValueError(
                    "ValidateGraphToApply: invalid after graph: "
                    f"{graph_error or 'unknown validation error'}"
                )

            parser_output = (
                workflow_response.merged_response.parser_output
            )

            parsed_actions = (
                parser_output.actions
                if parser_output is not None
                else ParsedActions()
            )

            supplemented_graph, supplements = (
                await augment_graph_with_client_tasks(
                    validated_after_graph,
                    parsed_actions.edits,
                    coding_is_allowed=turn_ctx.coding_is_allowed,
                )
            )

            if isinstance(supplemented_graph, dict):
                supplemented_graph = ProcessGraph.model_validate(
                    supplemented_graph
                )

            if not isinstance(supplemented_graph, ProcessGraph):
                raise TypeError(
                    "augment_graph_with_client_tasks returned an invalid graph"
                )

            validated_dump = validated_after_graph.model_dump(
                by_alias=True
            )
            supplemented_dump = supplemented_graph.model_dump(
                by_alias=True
            )

            # Workflow edits have already been applied by the runtime.
            # Only apply changes introduced by client-side supplements.
            if supplemented_dump != validated_dump:
                apply_fn = (
                    turn_ctx.apply_from_agent
                    if turn_ctx.apply_from_agent
                    else turn_ctx.set_graph
                )
                apply_fn(supplemented_graph)
                turn_ctx.graph_ref[0] = supplemented_graph
            else:
                turn_ctx.graph_ref[0] = validated_after_graph

            current_graph = turn_ctx.graph_ref[0]

            previous_apply = turn_ctx.last_apply_result_ref[0]

            turn_ctx.last_apply_result_ref[0] = (
                await refresh_last_graph_apply_result(
                    previous_apply,
                    ApplyWorkflowEditsResult(
                        success=True,
                        graph=current_graph,
                        error=None,
                    ),
                    supplement_summary="; ".join(supplements),
                )
            )

        async def on_workflow_response(
            workflow_response: AgentWorkflowResponse,
            previous_graph: ProcessGraph,
        ) -> None:
            await reconcile_workflow_response(
                workflow_response,
                previous_graph=previous_graph,
            )

        async def run_workflow_turn(
            inputs: WorkflowInputs,
        ) -> AgentWorkflowResponse:
            previous_graph = turn_ctx.graph_ref[0]

            workflow_response = await turn_ctx.run_workflow_streaming(
                run_agent_workflow,
                inputs,
                overrides,
                _WORKFLOW_EXECUTION_TIMEOUT,
                _run_token=turn_ctx.token,
                workflow_path=_WORKFLOW_DESIGNER_WORKFLOW_PATH,
            )

            await on_workflow_response(
                workflow_response,
                previous_graph,
            )

            return workflow_response

        async def parser_output_follow_up_chain(
            resp: AgentWorkflowResponse,
        ) -> AgentWorkflowResponse | None:
            parser_ctx = ExecutionFollowUpContext(
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
                toast=lambda message: turn_ctx.toast(message),
                set_inline_status=turn_ctx.set_inline_status,
                append_message=turn_ctx.append_message,
                prepare_stream_row=turn_ctx.prepare_stream_row,
                normalize_user_message_for_workflow=(
                    normalize_user_message_for_workflow
                ),
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
                action_context=turn_actions,
                on_workflow_response=on_workflow_response,
            )

            return await run_execution_follow_up_chain_async(
                parser_ctx,
                resp,
                flags=PostEditFlags(
                    had_import_workflow=had_import_workflow,
                    had_todo=had_todo,
                    had_add_comment=had_add_comment,
                ),
            )


        try:
            last_user_content: str | None = None

            for message in reversed(turn_ctx.state.history or []):
                if (
                    str(message.get("role", "")).strip().lower()
                    == "user"
                ):
                    content = (
                        message.get("content")
                        or message.get("content_for_display")
                        or ""
                    )
                    last_user_content = str(content)
                    break

            user_message_for_workflow = (
                normalize_user_message_for_workflow(
                    last_user_content
                    if (
                        last_user_content is not None
                        and last_user_content.strip()
                    )
                    else message_for_workflow
                )
            )

            if await try_run_auto_delegate_before_turn(
                turn_ctx.delegate_request_ref,
                user_message_for_workflow,
                current_role_id=turn_ctx.profile,
            ):
                turn_ctx.set_inline_status(None)
                return

            turn_ctx.prepare_stream_row()

            runtime = await get_runtime_for_prompts(
                turn_ctx.graph_ref[0]
            )

            initial_inputs = build_agent_workflow_initial_inputs(
                user_message_for_workflow,
                turn_ctx.graph_ref[0],
                turn_ctx.last_apply_result_ref[0],
                (
                    turn_ctx.get_recent_changes()
                    if turn_ctx.get_recent_changes
                    else None
                ),
                runtime=runtime,
                coding_is_allowed=turn_ctx.coding_is_allowed,
                contribution_is_allowed=turn_ctx.contribution_is_allowed,
                previous_turn=await format_previous_turn(
                    turn_ctx.state.history[:-1]
                ),
                language_hint=wf_lang_cell[0],
                session_language=turn_ctx.state.session_language,
            )

            response = await run_workflow_turn(initial_inputs)

        except WorkflowTimeoutError as exc:
            turn_ctx.set_inline_status(None)

            content = (
                f"(Request timed out after "
                f"{getattr(exc, 'timeout_s', 300):.0f}s. "
                "Try again or check that the LLM/service is responding.)"
            )

            response = AgentWorkflowResponse(
                merged_response=MergeResponse(
                    reply="",
                    result=self.parse_error_result(content),
                )
            )

            result = response.merged_response.result
            turn_ctx.last_apply_result_ref[0] = failed_apply_result(
                content
            )

        except TypeError as exc:
            turn_ctx.set_inline_status(None)

            content = f"(Workflow error: {exc})"

            response = AgentWorkflowResponse(
                merged_response=MergeResponse(
                    reply="",
                    result=self.parse_error_result(content),
                )
            )

            result = response.merged_response.result
            turn_ctx.last_apply_result_ref[0] = failed_apply_result(
                content
            )

        else:
            chained = await parser_output_follow_up_chain(response)

            if chained is None:
                return

            response = chained

            merged = response.merged_response
            result = merged.result

            apply_result_value = self.get_apply_result(
                merged.status,
                result,
            )

            applied_ok = (
                isinstance(apply_result_value, dict)
                and apply_result_value.get("attempted") is True
                and apply_result_value.get("success") is True
            )

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
                    edit.action in COMMENT_ACTIONS
                    for edit in edits
                )

            delegate_output = merged.delegate_request

            if turn_ctx.delegate_request_ref is not None:
                delegate_to = get_optional_str(
                    delegate_output,
                    "delegate_to",
                )
                delegate_error = get_optional_str(
                    delegate_output,
                    "error",
                )

                if (
                    delegate_output.get("ok") is True
                    and delegate_to
                    and delegate_to.strip()
                ):
                    if (
                        delegate_to.strip().lower()
                        != (turn_ctx.profile or "").strip().lower()
                    ):
                        turn_ctx.delegate_request_ref[0] = (
                            delegate_output
                        )
                elif (
                    delegate_error
                    and turn_ctx.is_current_run(turn_ctx.token)
                ):
                    await turn_ctx.toast(delegate_error.strip()[:200])

            report_output = merged.report_output

            if (
                turn_ctx.is_current_run(turn_ctx.token)
                and report_output.get("ok")
            ):
                turn_ctx.set_inline_status("Generating file…")

                try:
                    from gui.components.settings import (
                        get_rag_update_workflow_path,
                    )
                    from runtime.run import run_workflow

                    rag_path = get_rag_update_workflow_path()

                    if rag_path.exists():
                        rag_overrides: WorkflowInputs = {
                            "rag_update": {
                                "rag_index_data_dir": str(
                                    turn_ctx.rag_index_dir
                                ),
                                "units_dir": str(UNITS_DIR),
                                "mydata_dir": str(turn_ctx.mydata_dir),
                                "embedding_model": (
                                    turn_ctx.rag_embedding_model
                                ),
                            }
                        }

                        await asyncio.to_thread(
                            run_workflow,
                            rag_path,
                            initial_inputs={},
                            unit_param_overrides=rag_overrides,
                            format="dict",
                        )

                except (TypeError, WorkflowTimeoutError):
                    pass

                if turn_ctx.is_current_run(turn_ctx.token):
                    turn_ctx.set_inline_status(None)

            content = (
                merged.reply.strip()
                or "(No response from the model.)"
            )

            if content == "(No response from the model.)" and (
                parser_output := merged.parser_output
            ) is not None and (
                parser_output.actions.edits or parser_output.actions.tool_actions
            ):
                content = "Workflow actions completed."


            workflow_errors = merged.workflow_errors

            user_message_missing = any(
                error
                and (
                    (
                        str(error[0]) == "llm_agent"
                        and (error[1] or "").strip()
                    )
                    or "placeholder" in (error[1] or "").lower()
                    or "no message" in (error[1] or "").lower()
                )
                for error in workflow_errors
            )

            if user_message_missing:
                content = (
                    "Your message didn't reach the model. "
                    "Please try sending again."
                )

            result["content_for_display"] = content

            result["apply_result"] = apply_result_value

            if (
                result.get("kind") != "apply_failed"
                and isinstance(apply_result_value, dict)
                and apply_result_value.get("attempted") is True
                and apply_result_value.get("success") is False
            ):
                result["kind"] = "apply_failed"

            if workflow_errors and turn_ctx.is_current_run(
                turn_ctx.token
            ):
                error_message = workflow_errors[0][1][:150]

                if len(workflow_errors) > 1:
                    error_message += (
                        f" (+{len(workflow_errors) - 1} more)"
                    )

                if user_message_missing:
                    await turn_ctx.toast(
                        "Your message didn't reach the model. "
                        "Please try again."
                    )
                else:
                    await turn_ctx.toast(
                        f"Workflow error: {error_message}"
                    )

        display_content = (
            result.get("content_for_display")
            if isinstance(result.get("content_for_display"), str)
            and result.get("content_for_display")
            else content
        )

        display_content = formulas_calc_display_appendix(response)

        meta = {
            "turn_id": turn_ctx.turn_id,
            "agent": turn_ctx.agent_display,
            "source": "agent_response",
            "workflow_response": {
                "reply": display_content,
                "result_kind": result.get("kind"),
            },
            "parsed_edits": [
                edit.model_dump(by_alias=True)
                if isinstance(edit, ModelDumpable)
                else edit
                for edit in turn_actions.edits
            ],
            "tool_actions": turn_actions.tool_actions,
            "apply": apply_meta_with_formulas_calc_tool_status(
                response,
                result.get("apply_result", {}),
            ),
        }

        if result.get("kind") == "parse_error":
            meta["format_error"] = True

        if follow_up_contexts_this_turn:
            meta["follow_up_contexts"] = (
                follow_up_contexts_this_turn
            )

        turn_ctx.append_message(
            "agent",
            display_content,
            meta=meta,
        )

        if not turn_ctx.is_current_run(turn_ctx.token):
            return

        turn_ctx.set_inline_status(None)

        # The graph has already been applied by the workflow runtime.
        # Post-execution rounds are terminal: they may summarize or plan, but must
        # not emit tools or graph edits because there is no later round to process
        # them.
        parser_output = response.merged_response.parser_output

        final_content_holder = [content]

        final_ctx = PostExecutionFollowUpContext(
            graph_ref=turn_ctx.graph_ref,
            state=turn_ctx.state,
            token=turn_ctx.token,
            turn_id=turn_ctx.turn_id,
            agent_role_id=turn_ctx.profile,
            agent_label=turn_ctx.agent_display,
            max_rounds=max_wd_follow_ups,
            wf_language_hint=wf_lang_cell,
            is_current_run=turn_ctx.is_current_run,
            toast=lambda message: turn_ctx.toast(message),
            set_inline_status=turn_ctx.set_inline_status,
            append_message=turn_ctx.append_message,
            prepare_stream_row=turn_ctx.prepare_stream_row,
            normalize_user_message_for_workflow=(
                normalize_user_message_for_workflow
            ),
            last_apply_result_ref=turn_ctx.last_apply_result_ref,
            get_recent_changes=turn_ctx.get_recent_changes,
            overrides=overrides,
            run_workflow_streaming=turn_ctx.run_workflow_streaming,
            get_runtime_for_prompts=get_runtime_for_prompts,
            format_previous_turn=format_previous_turn,
            replace_agent_message_row=turn_ctx.replace_agent_message_row,
            stream_buffer_ref=turn_ctx.stream_buffer_ref,
            agent_workflow_path=_WORKFLOW_DESIGNER_WORKFLOW_PATH,
            record_llm_prompt_view=turn_ctx.record_llm_prompt_view,
            action_context=turn_actions,
            on_workflow_response=on_workflow_response,
        )

        await run_post_execution_follow_up_chain_async(
            final_ctx,
            result=result,
            content_holder=final_content_holder,
            parser_chain_runner=parser_output_follow_up_chain,
            flags=PostEditFlags(
                had_import_workflow=had_import_workflow,
                had_todo=had_todo,
                had_add_comment=had_add_comment,
            ),
        )

        finalize_workflow_designer_turn_session_language(
            turn_ctx.state,
            response,
            debug_log=turn_ctx.workflow_debug_log,
        )

        turn_ctx.persist_history_debounced()
