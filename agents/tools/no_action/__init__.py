"""no_action: stop signal from LLM to the follow-up runner."""

from __future__ import annotations

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.no_action.prompt import NO_ACTION_FOLLOW_UP_PREFIX
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput


async def run_no_action_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """No-operation"""
    _ = language_hint
    return FollowUpContribution(
        context_chunks=[NO_ACTION_FOLLOW_UP_PREFIX],
        any_empty_tool=False
    )
