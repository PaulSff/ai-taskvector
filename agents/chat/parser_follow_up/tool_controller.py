from __future__ import annotations

from agents.chat.context.follow_up_context import ParserFollowUpContext


def follow_up_tool_enabled(ctx: ParserFollowUpContext, tool_id: str) -> bool:
    """If ``follow_up_tool_ids`` is set, only listed tools run; empty tuple disables all tools."""
    allowed = ctx.follow_up_tool_ids
    if allowed is None:
        return True
    return tool_id in allowed
