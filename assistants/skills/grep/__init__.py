"""
grep follow-up: inject grep tool output from the prior assistant workflow response.
"""
from __future__ import annotations

from typing import Any, Callable

from assistants.skills.follow_up_common import TOOL_EMPTY_RESULT_LINE
from assistants.skills.grep.follow_ups import GREP_FOLLOW_UP_PREFIX, GREP_FOLLOW_UP_SUFFIX
from assistants.skills.types import FollowUpContribution


async def run_grep_follow_up(
    ctx: Any,
    _po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    """
    Build follow-up context from ``grep_output`` on the workflow response.

    ``ctx`` may provide ``follow_up_source_response`` (``dict``): the merge_response-shaped
    workflow dict for this turn (set by ``run_parser_output_follow_up_chain``).
    """
    try:
        setter = getattr(ctx, "set_inline_status", None)
        if callable(setter):
            setter("Grep result…")
    except Exception:
        pass
    hint = language_hint
    try:
        wf = getattr(ctx, "follow_up_source_response", None)
        if not isinstance(wf, dict):
            wf = {}
        grep_out = wf.get("grep_output")
        text = ""
        if isinstance(grep_out, dict):
            text = (grep_out.get("out") or grep_out.get("data") or "").strip()
            err = grep_out.get("error")
            if isinstance(err, str) and err.strip():
                text = f"{text}\nError: {err}".strip() if text else f"Error: {err}"
        elif grep_out is not None:
            text = str(grep_out).strip()
        body = text if text else TOOL_EMPTY_RESULT_LINE
        chunk = (
            GREP_FOLLOW_UP_PREFIX
            + body
            + GREP_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=not bool(text),
        )
    except Exception:
        chunk = (
            GREP_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + GREP_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk], any_empty_tool=True)


__all__ = ["run_grep_follow_up"]
