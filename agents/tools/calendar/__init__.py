"""Calendar follow-up: execute a calendar action through the calendar workflow."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import TypeAdapter, ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import (
    FOLLOW_UP_EXTRA_CALENDAR_FOLLOW_UP,
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 60.0


def _empty_calendar_contribution(
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    from agents.tools.calendar.follow_ups import (
        CALENDAR_FOLLOW_UP_PREFIX,
        CALENDAR_FOLLOW_UP_SUFFIX,
    )

    language = language_hint()

    return FollowUpContribution(
        context_chunks=[
            CALENDAR_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + CALENDAR_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        ],
        any_empty_tool=True,
        extra={FOLLOW_UP_EXTRA_CALENDAR_FOLLOW_UP: True},
    )


def _extract_calendar_result(out: object) -> str:
    """Extract and serialize the calendar workflow result."""

    if not isinstance(out, Mapping):
        return ""

    calendar_out = out.get("calendar")

    if not isinstance(calendar_out, Mapping):
        return ""

    calendar_data = calendar_out.get("data")
    calendar_error = calendar_out.get("error") or ""

    if isinstance(calendar_data, Mapping):
        if calendar_data.get("ok") is True:
            return str(dict(calendar_data)).strip()

        return str(
            calendar_data.get("error")
            or calendar_error
            or ""
        ).strip()

    if calendar_data is not None:
        return str(calendar_data).strip()

    return str(calendar_error).strip()


def _safe_set_inline_status(
    ctx: ExecutionFollowUpContext,
    status: str,
) -> None:
    try:
        ctx.set_inline_status(status)
    except (AttributeError, TypeError):
        pass


async def _safe_toast(
    ctx: ExecutionFollowUpContext,
    message: str,
) -> None:
    try:
        if ctx.is_current_run(ctx.token):
            await ctx.toast(message)
    except (AttributeError, TypeError, IndexError):
        pass


async def run_calendar_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep workflow and action-block imports local to avoid registration cycles.
    from agents.chat.agent_workflow import (
        CALENDAR_WORKFLOW_PATH,
        run_workflow_with_errors,
    )
    from agents.tools.calendar.action_block import CalendarActionBlock
    from agents.tools.calendar.follow_ups import (
        CALENDAR_FOLLOW_UP_PREFIX,
        CALENDAR_FOLLOW_UP_SUFFIX,
    )

    _safe_set_inline_status(ctx, "Using calendar…")

    try:
        calendar_actions = po.actions.get_tool_actions("calendar")

        if not calendar_actions:
            raise ValueError(
                "Calendar follow-up was requested, but no calendar action "
                "was found"
            )

        if len(calendar_actions) != 1:
            raise ValueError(
                "Expected exactly one calendar action, "
                f"got {len(calendar_actions)}"
            )

        raw_action = calendar_actions[0]

        try:
            action = TypeAdapter(CalendarActionBlock).validate_python(raw_action)
        except ValidationError as exc:
            raise ValueError(
                "Invalid calendar action block: "
                f"{raw_action!r}; errors={exc.errors()!r}"
            ) from exc

        action_obj = action.model_dump(
            mode="json",
            by_alias=True,
        )


        print(
            "calendar_follow_up: executing action",
            {
                "method": action_obj.get("method"),
            },
            flush=True,
        )

        out, errs = await run_workflow_with_errors(
            CALENDAR_WORKFLOW_PATH,
            initial_inputs={
                "trigger_inject": {
                    "template": action_obj,
                }
            },
            unit_param_overrides=None,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            print(
                "calendar_follow_up: workflow errors",
                {"errors": errs},
                flush=True,
            )
            await _safe_toast(
                ctx,
                f"Calendar error: {errs[0][1][:120]}",
            )

        result = _extract_calendar_result(out)

        if not result:
            print(
                "calendar_follow_up: returning empty tool result",
                flush=True,
            )
            return _empty_calendar_contribution(language_hint)

        language = language_hint()

        print(
            "calendar_follow_up: returning non-empty context chunk",
            flush=True,
        )

        return FollowUpContribution(
            context_chunks=[
                CALENDAR_FOLLOW_UP_PREFIX
                + result
                + CALENDAR_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            ],
            any_empty_tool=False,
            extra={FOLLOW_UP_EXTRA_CALENDAR_FOLLOW_UP: True},
        )

    except TimeoutError:
        await _safe_toast(ctx, "Calendar operation timed out")
        return _empty_calendar_contribution(language_hint)

    except ValidationError as exc:
        await _safe_toast(
            ctx,
            f"Invalid calendar action: {str(exc)[:120]}",
        )
        raise

    except (KeyError, TypeError, ValueError, IndexError) as exc:
        print(
            "calendar_follow_up: crashed",
            {
                "type": type(exc).__name__,
                "message": str(exc)[:300],
            },
            flush=True,
        )

        await _safe_toast(
            ctx,
            "Calendar workflow crashed: "
            f"{type(exc).__name__}: {str(exc)[:120]}",
        )

        raise


__all__ = ["run_calendar_follow_up"]
