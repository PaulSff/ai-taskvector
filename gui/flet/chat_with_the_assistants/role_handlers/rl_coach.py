"""RL Coach assistants chat turn (extracted from ``chat.py``)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from assistants.roles import RL_COACH_ROLE_ID, get_role
from assistants.roles.rl_coach.workflow_inputs import build_rl_coach_initial_inputs
from gui.flet.chat_with_the_assistants.chat_turn_context import format_previous_turn
from gui.flet.chat_with_the_assistants.role_handlers.turn_edits import canonicalize_add_comment_edits
from gui.flet.chat_with_the_assistants.rl_coach_handler import (
    build_rl_coach_unit_param_overrides,
    get_training_config_dict,
    get_training_config_summary,
    get_training_results_follow_up,
    run_rl_coach_workflow,
)
from gui.flet.chat_with_the_assistants.role_handlers.context import RoleChatTurnContext
from runtime.run import WorkflowTimeoutError


class RlCoachChatHandler:
    """Runs one RL Coach workflow turn and optional training-config save."""

    @property
    def role_id(self) -> str:
        return RL_COACH_ROLE_ID

    @property
    def display_name(self) -> str:
        return get_role(RL_COACH_ROLE_ID).display_name

    async def run_turn(self, turn_ctx: RoleChatTurnContext, *, message_for_workflow: str) -> None:
        training_config_summary = await asyncio.to_thread(get_training_config_summary)
        training_results = get_training_results_follow_up()
        previous_turn = format_previous_turn(turn_ctx.state.history[:-1])
        training_config_dict = await asyncio.to_thread(get_training_config_dict)
        initial_inputs = build_rl_coach_initial_inputs(
            message_for_workflow,
            training_config=training_config_summary,
            training_results=training_results,
            previous_turn=previous_turn,
            training_config_dict=training_config_dict,
        )
        overrides = build_rl_coach_unit_param_overrides(
            turn_ctx.provider,
            turn_ctx.cfg,
            rag_persist_dir=str(turn_ctx.rag_index_dir),
            rag_embedding_model=turn_ctx.rag_embedding_model,
        )
        turn_ctx.prepare_stream_row()
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
        wf_result = response.get("result")
        if isinstance(wf_result, dict):
            canonicalize_add_comment_edits(wf_result.get("edits"), assistant_role_id=turn_ctx.profile)
        raw = (response.get("reply") or "").strip() or "(No response from model.)"
        turn_ctx.clear_stream_row()
        turn_ctx.set_inline_status(None)
        workflow_errors = response.get("workflow_errors") or []
        if workflow_errors and turn_ctx.is_current_run(turn_ctx.token):
            await turn_ctx.toast(f"Workflow error: {workflow_errors[0][1][:120]}")
        turn_ctx.append_message(
            "assistant",
            raw,
            meta={
                "turn_id": turn_ctx.turn_id,
                "assistant": turn_ctx.assistant_display,
                "source": "assistant_response",
                "workflow_response": {"reply": raw},
            },
        )
        applied_config = response.get("applied_config")
        if applied_config and turn_ctx.is_current_run(turn_ctx.token):
            try:
                import yaml
                from gui.flet.components.settings import REPO_ROOT

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
