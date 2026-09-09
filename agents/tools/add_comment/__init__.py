"""add_comment: graph comment JSON action (prompt line) and post-apply review strings.

Parser-output follow-up is reserved for a future ``add_comment`` key on ``parser_output``;
today comments are applied as normal graph ``edits``."""

from __future__ import annotations

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput


async def run_add_comment_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """No-op unless ``parser_output`` gains an ``add_comment`` slice (future)."""
    _ = language_hint
    return FollowUpContribution(context_chunks=[], any_empty_tool=False)
