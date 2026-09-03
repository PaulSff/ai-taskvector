"""todo_manager: graph TODO list JSON actions (prompt line) and post-apply review strings.

Parser-output follow-up: reserved for a future ``todo_manager`` key on ``parser_output``;
today TODO edits are applied as normal graph ``edits`` and post-apply messaging uses
``follow_ups`` constants below."""

from __future__ import annotations

from agents.chat.context.follow_up_context import ParserFollowUpContext
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput


async def run_todo_manager_follow_up(
    _ctx: ParserFollowUpContext,
    _po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """No-op unless ``parser_output`` gains a ``todo_manager`` slice (future)."""
    _ = language_hint
    return FollowUpContribution(context_chunks=[], any_empty_tool=False)
