"""Analyst agents chat turn (extracted from ``chat.py``).

workflow response
    ├─ runtime applies workflow edits inline (during the workflow execution)
    ├─ graph now contains after_graph
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
    )
"""

from __future__ import annotations

import logging

from agents.chat.agent_workflow import (
    AgentWorkflowResponse,
    MergeResponse,
    build_agent_workflow_unit_param_overrides,
    get_runtime_for_prompts,
    refresh_last_graph_apply_result,
    run_agent_workflow,
)
from agents.chat.agent_workflow.helpers import (
    validate_graph_to_apply_inline,
)
from agents.chat.agent_workflow.workflow_inputs import (
    build_agent_workflow_initial_inputs,
    default_wf_language_hint,
)
from agents.chat.context import PostExecutionFollowUpContext
from agents.chat.context.follow_up_context import (
    ExecutionFollowUpContext,
    PostEditFlags,
)
from agents.chat.context.language_control import (
    finalize_workflow_designer_turn_session_language,
)
from agents.chat.context.role_turn_context import RoleChatTurnContext
from agents.chat.context.todo_list_manager import get_summary_params
from agents.chat.context.todo_list_manager.todo_list_manager import (
    augment_graph_with_client_tasks,
)
from agents.chat.follow_up_executor import (
    run_execution_follow_up_chain_async,
    run_post_execution_follow_up_chain_async,
)
from agents.chat.handlers.chat_turn_context import (
    format_previous_turn,
    normalize_user_message_for_workflow,
)
from agents.roles import ANALYST_ROLE_ID, get_role
from agents.roles.registry import is_role_light_graph_mode_enabled
from agents.roles.workflow_path import get_role_chat_workflow_path
from agents.tools.catalog import ordered_tools_for_role_id
from agents.tools.types import ParsedActions, ParserOutput
from core.schemas import ProcessGraph
from core.schemas.graph_edit_api import (
    COMMENT_ACTIONS,
    IMPORT_WORKFLOW_ACTION,
    TODO_ACTIONS,
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
)
from core.schemas.primitives import (
    ModelDumpable,
    WorkflowInputs,
)
from config.settings import get_workflow_designer_max_follow_ups
from runtime.run import WorkflowTimeoutError
from services.logging import setup_colored_logging

_AGENT_ROLE_ID = ANALYST_ROLE_ID
_AGENT_WORKFLOW_PATH = get_role_chat_workflow_path(_AGENT_ROLE_ID).resolve()
_IS_LIGHT_GRAPH_MODE_ENABLED = is_role_light_graph_mode_enabled(_AGENT_ROLE_ID)
_WORKFLOW_EXECUTION_TIMEOUT = None # default

logger = setup_colored_logging(logging.DEBUG)


class AnalystChatHandler:
    """Runs one Workflow Designer turn."""

    @property
    def role_id(self) -> str:
        return _AGENT_ROLE_ID

    @property
    def role_name(self) -> str:
        return get_role(self.role_id).role_name

    @staticmethod
    def apply_failure_result(
        content: str,
        graph: ProcessGraph,
        *,
        error_reason: str | None = None,
    ) -> AgentApplyWorkflowEditsResult:
        return AgentApplyWorkflowEditsResult(
            kind="apply_failed",
            content_for_display=content,
            graph=graph,
            edits=[],
            error_reason=error_reason or content,
            last_apply_result=ApplyWorkflowEditsResult(
                attempted=False,
                success=False,
                error=error_reason or content,
                graph_after=graph,
                edits_summary=None,
            ),
        )

    async def run_turn(
        self,
        turn_ctx: RoleChatTurnContext,
        *,
        message_for_workflow: str,
    ) -> None:
        response = AgentWorkflowResponse()
        content = ""
        result: AgentApplyWorkflowEditsResult | None = None
        updated_graph = turn_ctx.graph_ref[0]
        apply_result: ApplyWorkflowEditsResult | None = None
        apply_meta: dict = {}
        follow_up_contexts_this_turn: list[str] = []

        # A successful turn clears an error left by a previous execution.
        turn_ctx.error_ref[0] = None

        def publish_state() -> None:
            assert result is not None, (
                "Cannot publish workflow state without an agent result"
            )

            turn_ctx.graph_ref[0] = updated_graph
            turn_ctx.last_apply_result_ref[0] = apply_result
            turn_ctx.content_ref[0] = content
            turn_ctx.result_ref[0] = result
            turn_ctx.response_ref[0] = response
            turn_ctx.follow_up_contexts_ref[0] = list(
                follow_up_contexts_this_turn
            )
            turn_ctx.apply_meta_ref[0] = apply_meta


        overrides: WorkflowInputs = (
            build_agent_workflow_unit_param_overrides(
                role_id=_AGENT_ROLE_ID,
            )
        )

        graph = turn_ctx.graph_ref[0]

        validated_graph, validation_error = (
            await validate_graph_to_apply_inline(graph)
        )

        if validation_error is not None or validated_graph is None:
            error = ValueError(
                validation_error or "Graph validation returned no graph"
            )

            turn_ctx.error_ref[0] = {
                "type": "RoleExecutionError",
                "error": str(error),
            }

            content = f"(Role execution error: {error})"
            updated_graph = turn_ctx.graph_ref[0]
            result = self.apply_failure_result(
                content,
                updated_graph,
                error_reason=str(error),
            )
            apply_result = result.last_apply_result

            publish_state()
            return

        updated_graph = validated_graph
        turn_ctx.graph_ref[0] = updated_graph

        overrides["graph_summary"] = get_summary_params(
            turn_ctx.coding_is_allowed,
            validated_graph,
        )

        wf_lang_cell = [
            default_wf_language_hint(turn_ctx.state.session_language)
        ]

        wd_role = get_role(_AGENT_ROLE_ID)
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
                for tid, _ in ordered_tools_for_role_id(_AGENT_ROLE_ID)
            )
        )

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
            parser_output = merged.parser_output

            if parser_output is None:
                return

            actions = parser_output.actions
            turn_actions.edits.extend(actions.edits)

            for action, values in actions.tool_actions.items():
                turn_actions.tool_actions.setdefault(action, []).extend(values)

            agent_result = merged.result

            if agent_result is None:
                return

            workflow_apply_result = agent_result.last_apply_result

            if workflow_apply_result is None:
                return

            applied_ok = (
                workflow_apply_result.attempted
                and workflow_apply_result.success
            )

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
        ) -> None:
            nonlocal updated_graph
            nonlocal apply_result
            nonlocal apply_meta

            collect_actions(workflow_response)

            merged = workflow_response.merged_response
            after_graph = merged.graph

            if after_graph is None:
                raise ValueError(
                    "Workflow response did not contain an after graph"
                )

            validated_after_graph, graph_error = (
                await validate_graph_to_apply_inline(after_graph)
            )

            if graph_error is not None or validated_after_graph is None:
                raise ValueError(
                    "ValidateGraphToApply: invalid after graph: "
                    f"{graph_error or 'unknown validation error'}"
                )

            parser_output = merged.parser_output
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

            validated_dump = validated_after_graph.model_dump(
                by_alias=True
            )
            supplemented_dump = supplemented_graph.model_dump(
                by_alias=True
            )

            if supplemented_dump != validated_dump:
                apply_fn = (
                    turn_ctx.apply_from_agent
                    if turn_ctx.apply_from_agent
                    else turn_ctx.set_graph
                )
                apply_fn(supplemented_graph)
                updated_graph = supplemented_graph
            else:
                updated_graph = validated_after_graph

            turn_ctx.graph_ref[0] = updated_graph

            previous_apply = turn_ctx.last_apply_result_ref[0]

            apply_result = await refresh_last_graph_apply_result(
                previous_apply,
                ApplyWorkflowEditsResult(
                    attempted=True,
                    success=True,
                    graph_after=updated_graph,
                    error=None,
                ),
                supplement_summary="; ".join(supplements),
            )

            turn_ctx.last_apply_result_ref[0] = apply_result

        async def on_workflow_response(
            workflow_response: AgentWorkflowResponse,
        ) -> None:
            await reconcile_workflow_response(workflow_response)

        async def run_workflow_turn(
            inputs: WorkflowInputs,
        ) -> AgentWorkflowResponse:
            return await turn_ctx.run_workflow_streaming(
                run_agent_workflow,
                inputs,
                overrides,
                _WORKFLOW_EXECUTION_TIMEOUT,
                _run_token=turn_ctx.token,
                workflow_path=_AGENT_WORKFLOW_PATH,
            )

        async def parser_output_follow_up_chain(
            resp: AgentWorkflowResponse,
        ) -> AgentWorkflowResponse | None:
            parser_output = resp.merged_response.parser_output

            if parser_output is None:
                return None

            parser_ctx = ExecutionFollowUpContext(
                graph_ref=turn_ctx.graph_ref,
                state=turn_ctx.state,
                token=turn_ctx.token,
                turn_id=turn_ctx.turn_id,
                agent_label=turn_ctx.agent_label,
                follow_up_contexts=follow_up_contexts_this_turn,
                max_rounds=max_wd_follow_ups,
                wf_language_hint=wf_lang_cell,
                is_current_run=turn_ctx.is_current_run,
                toast=lambda message: turn_ctx.toast(message),
                set_inline_status=turn_ctx.set_inline_status,
                append_message=turn_ctx.append_message,
                normalize_user_message_for_workflow=(
                    normalize_user_message_for_workflow
                ),
                last_apply_result_ref=turn_ctx.last_apply_result_ref,
                get_recent_changes=turn_ctx.get_recent_changes,
                overrides=overrides,
                run_workflow_streaming=turn_ctx.run_workflow_streaming,
                get_runtime_for_prompts=get_runtime_for_prompts,
                format_previous_turn=format_previous_turn,
                follow_up_tool_ids=wd_follow_up_tools,
                follow_up_source_response=None,
                agent_role_id=_AGENT_ROLE_ID,
                record_llm_prompt_view=turn_ctx.record_llm_prompt_view,
                action_context=parser_output,
                on_workflow_response=on_workflow_response,
                light_graph_mode=_IS_LIGHT_GRAPH_MODE_ENABLED,
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
                    message_content = (
                        message.get("content")
                        or message.get("content_for_display")
                        or ""
                    )
                    last_user_content = str(message_content)
                    break

            user_message_for_workflow = normalize_user_message_for_workflow(
                last_user_content
                if last_user_content is not None
                and last_user_content.strip()
                else message_for_workflow
            )

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
                light_graph_mode=_IS_LIGHT_GRAPH_MODE_ENABLED,
            )

            response = await run_workflow_turn(initial_inputs)
            await on_workflow_response(response)

            chained = await parser_output_follow_up_chain(response)

            if chained is not None:
                response = chained

            merged = response.merged_response
            result = merged.result

            if result is None:
                raise ValueError(
                    "Workflow response did not contain an agent result"
                )

            apply_result = result.last_apply_result

            content = (
                merged.reply.strip()
                or "(No response from the model.)"
            )

            parser_output = merged.parser_output

            if (
                content == "(No response from the model.)"
                and parser_output is not None
                and (
                    parser_output.actions.edits
                    or parser_output.actions.tool_actions
                )
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

            if (
                result.kind != "apply_failed"
                and result.last_apply_result is not None
                and result.last_apply_result.attempted
                and not result.last_apply_result.success
            ):
                result.kind = "apply_failed"

            result.content_for_display = content

            if workflow_errors and turn_ctx.is_current_run(
                turn_ctx.token
            ):
                error_message = workflow_errors[0][1][:150]

                if len(workflow_errors) > 1:
                    error_message += (
                        f" (+{len(workflow_errors) - 1} more)"
                    )

                await turn_ctx.toast(
                    (
                        "Your message didn't reach the model. "
                        "Please try again."
                    )
                    if user_message_missing
                    else f"Workflow error: {error_message}"
                )

        except WorkflowTimeoutError as exc:
            turn_ctx.set_inline_status(None)

            content = (
                f"(Request timed out after "
                f"{getattr(exc, 'timeout_s', 300):.0f}s. "
                "Try again or check that the LLM/service is responding.)"
            )

            updated_graph = turn_ctx.graph_ref[0]
            result = self.apply_failure_result(
                content,
                updated_graph,
                error_reason=content,
            )
            response = AgentWorkflowResponse(
                merged_response=MergeResponse(
                    reply="",
                    result=result,
                )
            )
            apply_result = result.last_apply_result

        except TypeError as exc:
            turn_ctx.set_inline_status(None)

            content = f"(Workflow error: {exc})"
            updated_graph = turn_ctx.graph_ref[0]
            result = self.apply_failure_result(
                content,
                updated_graph,
                error_reason=content,
            )
            response = AgentWorkflowResponse(
                merged_response=MergeResponse(
                    reply="",
                    result=result,
                )
            )
            apply_result = result.last_apply_result

        except Exception as exc:
            logger.exception("Unexpected error during role execution")

            turn_ctx.set_inline_status(None)

            turn_ctx.error_ref[0] = {
                "type": "RoleExecutionError",
                "error": str(exc),
            }

            content = f"(Role execution error: {exc})"
            updated_graph = turn_ctx.graph_ref[0]
            result = self.apply_failure_result(
                content,
                updated_graph,
                error_reason=str(exc),
            )
            response = AgentWorkflowResponse(
                merged_response=MergeResponse(
                    reply="",
                    result=result,
                )
            )
            apply_result = result.last_apply_result

        content_for_display = result.content_for_display

        if not content_for_display:
            content_for_display = content

        content = content_for_display
        result.content_for_display = content

        meta = {
            "turn_id": turn_ctx.turn_id,
            "agent": turn_ctx.agent_label,
            "source": "agent_response",
            "workflow_response": {
                "reply": content,
                "result_kind": result.kind,
            },
            "parsed_edits": [
                edit.model_dump(by_alias=True)
                if isinstance(edit, ModelDumpable)
                else edit
                for edit in turn_actions.edits
            ],
            "tool_actions": turn_actions.tool_actions,
            "apply": apply_meta,
        }

        if result.kind == "apply_failed":
            meta["format_error"] = True

        if follow_up_contexts_this_turn:
            meta["follow_up_contexts"] = (
                follow_up_contexts_this_turn
            )

        if turn_ctx.is_current_run(turn_ctx.token):
            turn_ctx.append_message(
                "agent",
                content,
                meta=meta,
            )

        updated_graph = turn_ctx.graph_ref[0]
        publish_state()

        if not turn_ctx.is_current_run(turn_ctx.token):
            return

        turn_ctx.set_inline_status(None)

        parser_output = response.merged_response.parser_output
        final_content_holder = [content]

        final_ctx = PostExecutionFollowUpContext(
            graph_ref=turn_ctx.graph_ref,
            state=turn_ctx.state,
            token=turn_ctx.token,
            turn_id=turn_ctx.turn_id,
            agent_role_id=turn_ctx.role_id,
            agent_label=turn_ctx.agent_label,
            max_rounds=max_wd_follow_ups,
            wf_language_hint=wf_lang_cell,
            is_current_run=turn_ctx.is_current_run,
            toast=lambda message: turn_ctx.toast(message),
            set_inline_status=turn_ctx.set_inline_status,
            append_message=turn_ctx.append_message,
            normalize_user_message_for_workflow=(
                normalize_user_message_for_workflow
            ),
            last_apply_result_ref=turn_ctx.last_apply_result_ref,
            get_recent_changes=turn_ctx.get_recent_changes,
            overrides=overrides,
            run_workflow_streaming=turn_ctx.run_workflow_streaming,
            get_runtime_for_prompts=get_runtime_for_prompts,
            format_previous_turn=format_previous_turn,
            stream_buffer_ref=turn_ctx.stream_buffer_ref,
            agent_workflow_path=_AGENT_WORKFLOW_PATH,
            record_llm_prompt_view=turn_ctx.record_llm_prompt_view,
            action_context=(
                parser_output
                if parser_output is not None
                else ParserOutput()
            ),
            on_workflow_response=on_workflow_response,
            light_graph_mode=_IS_LIGHT_GRAPH_MODE_ENABLED,
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

        content = final_content_holder[0]
        result.content_for_display = content
        updated_graph = turn_ctx.graph_ref[0]

        publish_state()

        finalize_workflow_designer_turn_session_language(
            turn_ctx.state,
            response,
            debug_log=turn_ctx.workflow_debug_log,
        )

        turn_ctx.persist_history_debounced()
