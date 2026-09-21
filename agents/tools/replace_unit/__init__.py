"""replace_unit follow-up runner (no-op).
"""

from __future__ import annotations

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput


async def run_replace_unit_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """No-op unless ``parser_output`` gains an ``replace_unit`` slice (future)."""
    _ = language_hint
    return FollowUpContribution(context_chunks=[], any_empty_tool=False)
