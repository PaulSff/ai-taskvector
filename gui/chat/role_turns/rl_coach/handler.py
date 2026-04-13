"""RL Coach assistants chat turn (extracted from ``chat.py``)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from assistants.roles import RL_COACH_ROLE_ID, get_role
from assistants.roles.rl_coach.workflow_inputs import (
    build_rl_coach_assistant_aligned_initial_inputs,
    build_rl_coach_training_inject_updates,
)
from assistants.roles.workflow_designer.workflow_inputs import default_wf_language_hint
from assistants.roles.workflow_path import get_role_chat_workflow_path
from assistants.tools.catalog import ORDERED_RL_COACH_TOOLS, rl_coach_tool_ids
from gui.chat.auto_delegate_turn import try_run_auto_delegate_before_turn
from gui.chat.chat_turn_context import format_previous_turn, normalize_user_message_for_workflow
from gui.chat.language_control import finalize_workflow_designer_turn_session_language
from gui.chat.llm_prompt_inspector import record_llm_prompt_view_if_present
from gui.chat.rag_context import _UNITS_DIR
from gui.chat.rl_coach_handler import (
    build_rl_coach_unit_param_overrides,
    get_training_config_dict,
    get_training_config_summary,
    get_training_results_follow_up,
    run_rl_coach_workflow,
)
from gui.chat.workflow_designer_followups import (
    ParserFollowUpContext,
    run_parser_output_follow_up_chain,
)
from gui.chat.workflow_designer_handler import get_runtime_for_prompts
from gui.components.settings import get_workflow_designer_max_follow_ups
from gui.utils.workflow_output_normalizer import (
    apply_meta_with_formulas_calc_tool_status,
    formulas_calc_display_appendix,
)
from ..context import RoleChatTurnContext
from ..turn_edits import canonicalize_add_comment_edits
from runtime.run import WorkflowTimeoutError

_RL_COACH_WORKFLOW_PATH = get_role_chat_workflow_path(RL_COACH_ROLE_ID).resolve()


class RlCoachChatHandler:
    """Runs RL Coach workflow with Analyst-style merge_response and parser follow-ups."""

    @property
    def role_id(self) -> str:
        return RL_COACH_ROLE_ID

    @property
    def role_name(self) -> str:
        return get_role(RL_COACH_ROLE_ID).role_name

    async def run_turn(self, turn_ctx: RoleChatTurnContext, *, message_for_workflow: str) -> None:
        last_user_content = None
        for m in reversed(turn_ctx.state.history or []):
            if isinstance(m, dict) and (m.get("role") or "").strip().lower() == "user":
                last_user_content = (m.get("content") or m.get("content_for_display") or "")
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

        report_dir = str(Path(turn_ctx.mydata_dir) / "reports")
        overrides = build_rl_coach_unit_param_overrides(
            turn_ctx.provider,
            turn_ctx.cfg,
            report_output_dir=report_dir,
        )
        overrides["graph_summary"] = {
            "include_code_block_source": False,
            "include_structure": False,
        }

        _graph = turn_ctx.graph_ref[0]
        follow_up_contexts_this_turn: list[str] = []
        wf_lang_cell = [default_wf_language_hint(turn_ctx.state.session_language)]
        _rl_role = get_role(RL_COACH_ROLE_ID)
        max_follow_ups = (
            _rl_role.follow_up_max_rounds
            if _rl_role.follow_up_max_rounds is not None
            else get_workflow_designer_max_follow_ups()
        )
        follow_up_tools = _rl_role.tools if _rl_role.tools else tuple(rl_coach_tool_ids())

        async def _extend_rl_inputs(
            base: dict[str, dict[str, Any]],
        ) -> dict[str, dict[str, Any]]:
            summary, tdict = await asyncio.gather(
                asyncio.to_thread(get_training_config_summary),
                asyncio.to_thread(get_training_config_dict),
            )
            results = get_training_results_follow_up()
            extra = build_rl_coach_training_inject_updates(summary, results, tdict)
            return {**base, **extra}

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
                assistant_role_id=RL_COACH_ROLE_ID,
                assistant_workflow_path=_RL_COACH_WORKFLOW_PATH,
                analyst_mode=True,
                ordered_follow_up_tools=ORDERED_RL_COACH_TOOLS,
                record_llm_prompt_view=turn_ctx.record_llm_prompt_view,
                extend_assistant_initial_inputs_async=_extend_rl_inputs,
            )
            return await run_parser_output_follow_up_chain(parser_ctx, resp)

        training_config_summary = await asyncio.to_thread(get_training_config_summary)
        training_results = get_training_results_follow_up()
        previous_turn = format_previous_turn(turn_ctx.state.history[:-1])
        training_config_dict = await asyncio.to_thread(get_training_config_dict)
        initial_inputs = build_rl_coach_assistant_aligned_initial_inputs(
            user_message_for_workflow,
            _graph,
            turn_ctx.last_apply_result_ref[0],
            turn_ctx.get_recent_changes() if turn_ctx.get_recent_changes else None,
            training_config=training_config_summary,
            training_results=training_results,
            previous_turn=previous_turn,
            training_config_dict=training_config_dict,
            runtime=get_runtime_for_prompts(_graph),
            coding_is_allowed=turn_ctx.coding_is_allowed,
            contribution_is_allowed=turn_ctx.contribution_is_allowed,
            language_hint=wf_lang_cell[0],
            session_language=turn_ctx.state.session_language,
            analyst_mode=True,
        )

        turn_ctx.prepare_stream_row()
        response: dict[str, Any] = {}
        try:
            response = await turn_ctx.run_workflow_streaming(
                run_rl_coach_workflow,
                initial_inputs,
                overrides,
                None,
                _run_token=turn_ctx.token,
            )
        except WorkflowTimeoutError as ex:
            turn_ctx.set_inline_status(None)
            content = f"(Request timed out after {getattr(ex, 'timeout_s', 300):.0f}s. Try again.)"
            response = {"reply": content, "workflow_errors": []}
            record_llm_prompt_view_if_present(response, turn_ctx.record_llm_prompt_view)
            turn_ctx.clear_stream_row()
            turn_ctx.set_inline_status(None)
            turn_ctx.append_message(
                "assistant",
                content,
                meta={
                    "turn_id": turn_ctx.turn_id,
                    "assistant": turn_ctx.assistant_display,
                    "source": "assistant_response",
                    "workflow_response": {"reply": content},
                },
            )
            finalize_workflow_designer_turn_session_language(
                turn_ctx.state, response, debug_log=turn_ctx.workflow_debug_log
            )
            turn_ctx.persist_history_debounced()
            return
        else:
            chained = await _parser_output_follow_up_chain(response)
            if chained is None:
                return
            response = chained

        record_llm_prompt_view_if_present(response, turn_ctx.record_llm_prompt_view)

        wf_result_early = response.get("result") or {}
        result_early = dict(wf_result_early) if isinstance(wf_result_early, dict) else {}
        dh_training = result_early.get("delegate_handoff")
        if turn_ctx.delegate_request_ref is not None and isinstance(dh_training, dict):
            if dh_training.get("ok") is True and (dh_training.get("delegate_to") or "").strip():
                if (dh_training.get("delegate_to") or "").strip().lower() != (
                    turn_ctx.profile or ""
                ).strip().lower():
                    turn_ctx.delegate_request_ref[0] = dh_training
                    turn_ctx.clear_stream_row()
                    turn_ctx.set_inline_status(None)
                    finalize_workflow_designer_turn_session_language(
                        turn_ctx.state, response, debug_log=turn_ctx.workflow_debug_log
                    )
                    turn_ctx.persist_history_debounced()
                    return
            err_dh = (dh_training.get("error") or "").strip() if isinstance(dh_training, dict) else ""
            if err_dh and turn_ctx.is_current_run(turn_ctx.token):
                await turn_ctx.toast(err_dh[:200])

        dr_out = response.get("delegate_request")
        if turn_ctx.delegate_request_ref is not None and isinstance(dr_out, dict):
            if dr_out.get("ok") is True and (dr_out.get("delegate_to") or "").strip():
                dt = (dr_out.get("delegate_to") or "").strip().lower()
                if dt != (turn_ctx.profile or "").strip().lower():
                    turn_ctx.delegate_request_ref[0] = dr_out
            else:
                err_d = (dr_out.get("error") or "").strip()
                if err_d and turn_ctx.is_current_run(turn_ctx.token):
                    await turn_ctx.toast(err_d[:200])

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
        content = (
            (raw_reply if isinstance(raw_reply, str) else str(raw_reply or "")).strip()
            or "(No response from model.)"
        )
        if content == "(No response from model.)":
            po = response.get("parser_output")
            edits = po if isinstance(po, list) else (po.get("edits") if isinstance(po, dict) else None)
            if isinstance(edits, list) and edits:
                content = "No tool actions requested."

        wf_result = response.get("result") or {}
        result = dict(wf_result) if isinstance(wf_result, dict) else {}
        canonicalize_add_comment_edits(result.get("edits"), assistant_role_id=turn_ctx.profile)

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

        content = content + formulas_calc_display_appendix(response)

        turn_ctx.clear_stream_row()
        turn_ctx.set_inline_status(None)
        if workflow_errors and turn_ctx.is_current_run(turn_ctx.token):
            err_msg = workflow_errors[0][1][:150] if workflow_errors else ""
            if len(workflow_errors) > 1:
                err_msg += f" (+{len(workflow_errors) - 1} more)"
            if user_message_missing:
                await turn_ctx.toast("Your message didn't reach the model. Please try again.")
            else:
                await turn_ctx.toast(f"Workflow error: {err_msg}")

        meta = {
            "turn_id": turn_ctx.turn_id,
            "assistant": turn_ctx.assistant_display,
            "source": "assistant_response",
            "workflow_response": {
                "reply": content,
                "result_kind": result.get("kind"),
            },
            "parsed_edits": result.get("edits", []),
            "apply": apply_meta_with_formulas_calc_tool_status(
                response,
                response.get("status") or {},
            ),
        }
        if follow_up_contexts_this_turn:
            meta["follow_up_contexts"] = follow_up_contexts_this_turn
        turn_ctx.append_message("assistant", content, meta=meta)

        applied_config = None
        if isinstance(result, dict) and result.get("kind") == "applied":
            applied_config = result.get("config")

        if applied_config and turn_ctx.is_current_run(turn_ctx.token):
            try:
                import yaml
                from gui.components.settings import REPO_ROOT

                path_str = (turn_ctx.training_config_path or "").strip()
                if path_str:
                    path = Path(path_str)
                    if not path.is_absolute() and REPO_ROOT is not None:
                        path = (REPO_ROOT / path_str).resolve()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("w", encoding="utf-8") as f:
                        yaml.dump(applied_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                    await turn_ctx.toast("Training config updated and saved.")
            except Exception:
                if turn_ctx.is_current_run(turn_ctx.token):
                    await turn_ctx.toast("Config was applied but save to file failed.")
        elif turn_ctx.is_current_run(turn_ctx.token):
            await turn_ctx.toast("RL Coach reply.")

        finalize_workflow_designer_turn_session_language(
            turn_ctx.state, response, debug_log=turn_ctx.workflow_debug_log
        )
        turn_ctx.persist_history_debounced()
