"""delegate_request: hand over the current request to another role."""

from __future__ import annotations

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput


async def run_delegate_request_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """No-op unless ``parser_output`` gains an ``delegate_request`` slice (future)."""
    _ = language_hint
    return FollowUpContribution(context_chunks=[], any_empty_tool=False)
