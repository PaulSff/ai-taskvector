"""report follow-up: summarize report_output from the prior workflow turn."""
from __future__ import annotations

from typing import Any, Callable

from assistants.skills.report.follow_ups import REPORT_FOLLOW_UP_SUFFIX
from assistants.skills.types import FollowUpContribution


async def run_report_follow_up(
    ctx: Any,
    _po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Report…")
    except Exception:
        pass
    wf = getattr(ctx, "follow_up_source_response", None)
    if not isinstance(wf, dict):
        wf = {}
    hint = language_hint
    ro = wf.get("report_output") or {}
    lines: list[str] = []
    if isinstance(ro, dict):
        if ro.get("ok"):
            pth = (ro.get("output_path") or "").strip()
            lines.append(
                "Report written successfully"
                + (f" to {pth}" if pth else "")
                + "."
            )
            prev = (ro.get("report_preview") or "").strip()
            if prev:
                lines.append("Preview:\n" + prev)
        else:
            err = (ro.get("error") or "").strip() or "unknown error"
            lines.append(f"Report failed: {err}")
    else:
        lines.append("Report action was processed.")
    body = "\n\n".join(lines)
    chunk = (
        "IMPORTANT: Report result from your previous turn.\n\n"
        + body
        + REPORT_FOLLOW_UP_SUFFIX.format(
            language=hint(),
            session_language=hint(),
        )
    )
    return FollowUpContribution(context_chunks=[chunk], any_empty_tool=False)


__all__ = ["run_report_follow_up"]
