"""
report follow-up: summarize report_output from the prior workflow turn.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.report.follow_ups import (
    REPORT_FOLLOW_UP_PREFIX,
    REPORT_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP,
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)


def _empty_report_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = hint()

    chunk = (
        REPORT_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + REPORT_FOLLOW_UP_SUFFIX.format(
            language=language,
            session_language=language,
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
        extra={FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP: True},
    )


def _validate_report_action(po: ParserOutput) -> None:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.report.action_block import ReportActionBlock

    report_actions = po.actions.get_tool_actions("report")

    if not report_actions:
        raise ValueError(
            "Report follow-up was requested, but no report action was found"
        )

    if len(report_actions) != 1:
        raise ValueError(
            "Report follow-up expected exactly one report action, "
            f"got {len(report_actions)}"
        )

    try:
        ReportActionBlock.model_validate(report_actions[0])
    except ValidationError as exc:
        raise ValueError(
            f"Invalid report action: {str(exc)[:120]}"
        ) from exc


def _format_report_output(report_output: object) -> str:
    if not isinstance(report_output, Mapping):
        return "Report was created."

    if report_output.get("ok"):
        output_path = str(report_output.get("output_path") or "").strip()
        result = (
            "Report written successfully"
            + (f" to {output_path}" if output_path else "")
            + "."
        )

        preview = str(report_output.get("report_preview") or "").strip()

        if preview:
            result += "\n\nPreview:\n" + preview

        return result

    error = str(report_output.get("error") or "").strip()
    return f"Report failed: {error or 'unknown error'}"


async def run_report_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Generating file…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    # Validate and normalize the parser action using the authoritative schema.
    # The validated action is not used to generate the summary because the
    # report output comes from the prior workflow turn.
    _validate_report_action(po)

    workflow_output = getattr(ctx, "follow_up_source_response", None)

    if not isinstance(workflow_output, Mapping):
        return _empty_report_contribution(hint)

    report_output = workflow_output.get("report_output")

    if report_output is None:
        return _empty_report_contribution(hint)

    body = _format_report_output(report_output)
    language = hint()

    chunk = (
        REPORT_FOLLOW_UP_PREFIX
        + body
        + REPORT_FOLLOW_UP_SUFFIX.format(
            language=language,
            session_language=language,
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=False,
        extra={FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP: True},
    )


__all__ = ["run_report_follow_up"]
