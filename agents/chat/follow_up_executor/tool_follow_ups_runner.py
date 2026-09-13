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
from agents.tools.registry import get_follow_up_runner
from agents.tools.types import LanguageHintGetter, ParserOutput

from .tool_controller import follow_up_tool_enabled


async def run_role_ordered_follow_ups(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    response: AgentWorkflowResponse,
    hint: LanguageHintGetter,
    acc: WDFollowUpAcc,
) -> None:
    # the ordered tools come either from the follow-up context or tools catalog
    ordered_tools = (
        getattr(ctx, "ordered_follow_up_tools", None)
        or ordered_tools_for_role_id(ctx.agent_role_id)
    )
    # select the tool_ids available for the role requesting
    for tool_id, parser_key in ordered_tools:
        if not follow_up_tool_enabled(ctx, tool_id):
            continue

        print(
            "\033[38;5;245m"
            "[parser_follow_up_chain] followup_tool_enabled "
            f"tool_id={tool_id}\033[0m",
            flush=True,
        )

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
        # get the runner for each tool_id
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
        # call the tool runner
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
        # merge the tool response into the context
        # for the LLM to inspect on the next turn
        merge_follow_up_contribution_into_acc(acc, contribution)
