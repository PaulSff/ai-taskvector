from __future__ import annotations

import traceback

from agents.chat.agent_workflow.wf_response_schema import AgentWorkflowResponse
from agents.chat.context.context_mergers import (
    merge_follow_up_contribution_into_acc,
)
from agents.chat.context.follow_up_context import (
    ExecutionFollowUpContext,
    WDFollowUpAcc,
)
from agents.tools.catalog import ordered_tools_for_role_id
from agents.tools.follow_up_common import (
    EDITS_FOLLOW_UP_PREFIX,
    FOLLOW_UP_RESPONSE_SESSION_SUFFIX,
)
from agents.tools.registry import get_follow_up_runner
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput
from core.schemas.graph_edit_api import ApplyWorkflowEditsResult
from runtime.tools_bootstrap import ensure_tools_registration

from .tool_controller import follow_up_tool_enabled


def build_edits_follow_up_chunk(
    result: ApplyWorkflowEditsResult | None,
    *,
    hint: LanguageHintGetter,
) -> str | None:
    if result is None or not result.attempted:
        return None

    result_text = (result.edits_summary or "").strip()
    if not result_text:
        return None

    lang = hint()
    return (
        EDITS_FOLLOW_UP_PREFIX
        + result_text
        + FOLLOW_UP_RESPONSE_SESSION_SUFFIX.format(
            language=lang,
            session_language=lang,
        )
    )


def build_edits_error_follow_up_chunk(
    error_reason: str | None,
    *,
    hint: LanguageHintGetter,
) -> str | None:
    if not error_reason:
        return None

    lang = hint()
    return (
        EDITS_FOLLOW_UP_PREFIX
        + error_reason
        + FOLLOW_UP_RESPONSE_SESSION_SUFFIX.format(
            language=lang,
            session_language=lang,
        )
    )


async def run_role_ordered_follow_ups(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    response: AgentWorkflowResponse,
    hint: LanguageHintGetter,
    acc: WDFollowUpAcc,
) -> None:
    ensure_tools_registration(role_id=ctx.agent_role_id)

    # Inline edits are handled without tool runners.
    if getattr(po.actions, "edits", None):
        last_apply_result: ApplyWorkflowEditsResult | None = (
            ctx.last_apply_result_ref[0] if ctx.last_apply_result_ref else None
        )
        chunk = build_edits_follow_up_chunk(last_apply_result, hint=hint)
        if chunk is not None:
            merge_follow_up_contribution_into_acc(
                acc,
                FollowUpContribution(
                    context_chunks=[chunk],
                    any_empty_tool=False,
                ),
            )

    error_chunk = build_edits_error_follow_up_chunk(
        getattr(po.actions, "error_reason", None),
        hint=hint,
    )
    if error_chunk is not None:
        merge_follow_up_contribution_into_acc(
            acc,
            FollowUpContribution(
                context_chunks=[error_chunk],
                any_empty_tool=False,
            ),
        )

    ordered_tools = (
        getattr(ctx, "ordered_follow_up_tools", None)
        or ordered_tools_for_role_id(ctx.agent_role_id)
    )

    for tool_id, parser_key in ordered_tools:
        if not follow_up_tool_enabled(ctx, tool_id):
            continue

        if not po.actions.has_tool_action(parser_key):
            continue

        actions = po.actions.get_tool_actions(parser_key)

        print(
            "[parser_follow_up_chain] "
            f"gate parser_key={parser_key} "
            f"action_count={len(actions)} "
            f"repr={repr(actions)[:400]}",
            flush=True,
        )

        runner = get_follow_up_runner(tool_id)
        if runner is None:
            raise RuntimeError(
                "No registered follow-up runner found for "
                f"tool_id={tool_id!r}, parser_key={parser_key!r}"
            )

        print(
            "\033[92m"
            "[parser_follow_up_chain] followup_runner_start "
            f"tool_id={tool_id} "
            f"parser_key={parser_key} "
            f"action_count={len(actions)}\033[0m",
            flush=True,
        )

        try:
            contribution = await runner(
                ctx,
                po,
                language_hint=hint,
            )
        except Exception as exc:
            print(
                "[parser_follow_up_chain] "
                "followup_runner_failed "
                f"tool_id={tool_id} "
                f"parser_key={parser_key}: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            traceback.print_exc()
            raise

        merge_follow_up_contribution_into_acc(acc, contribution)
