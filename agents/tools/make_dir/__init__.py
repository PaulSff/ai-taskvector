"""
make_dir follow-up: create one or more directories concurrently via the
make_dir workflow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    MAKE_DIR_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.make_dir.follow_ups import (
    MAKE_DIR_FOLLOW_UP_PREFIX,
    MAKE_DIR_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_make_dir_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = (hint() or "English").strip() or "English"

    chunk = (
        MAKE_DIR_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + MAKE_DIR_FOLLOW_UP_SUFFIX.format(
            language=language,
            session_language=language,
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
    )


def _format_workflow_error(errs: object) -> str:
    if not errs:
        return "unknown workflow error"

    try:
        first_error = errs[0]  # type: ignore[index]
    except (IndexError, TypeError):
        return str(errs)[:120]

    if isinstance(first_error, (tuple, list)) and len(first_error) > 1:
        return str(first_error[1])[:120]

    return str(first_error)[:120]


def _extract_make_dir_result(output: object) -> tuple[str, str]:
    if not isinstance(output, Mapping):
        return "", ""

    raw_data = output.get("data")
    raw_error = output.get("error")

    data = str(raw_data).strip() if raw_data is not None else ""
    error = ""

    if isinstance(raw_error, Mapping):
        if "error" in raw_error:
            raw_error = raw_error["error"]
        elif "message" in raw_error:
            raw_error = raw_error["message"]

    if raw_error is not None:
        error = str(raw_error).strip()

    return data, error


async def _run_one_make_dir(
    action: object,
) -> tuple[str, str | None]:
    """Run one normalized make_dir action."""

    payload: JsonValue = TypeAdapter(JsonValue).validate_python(
        action.model_dump(mode="json")  # type: ignore[union-attr]
    )

    out, errs = await run_workflow_with_errors(
        MAKE_DIR_WORKFLOW_PATH,
        initial_inputs={
            "inject_payload": {
                "template": payload,
            }
        },
        format="dict",
        execution_timeout_s=EXECUTION_TIMEOUT_S,
    )

    workflow_error = _format_workflow_error(errs) if errs else None

    make_dir_output: object = {}

    if isinstance(out, Mapping):
        make_dir_output = out.get("make_dir") or {}

    make_dir_data, make_dir_error = _extract_make_dir_result(
        make_dir_output
    )

    # Prefer an explicit error returned by the workflow.
    result = make_dir_error or make_dir_data

    if result:
        return result, None

    return "", workflow_error or make_dir_error


async def run_make_dir_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.make_dir.action_block import MakeDirActionBlock

    try:
        ctx.set_inline_status("Creating folders…")
    except (AttributeError, TypeError):
        pass

    try:
        raw_actions = po.actions.get_tool_actions("make_dir")

        if not raw_actions:
            raise ValueError(
                "Make-dir follow-up was requested, but no "
                "make_dir action was found"
            )

        # Validate every action before executing any workflow. This avoids
        # partial execution when a later action is malformed.
        actions = []

        for raw_action in raw_actions:
            try:
                actions.append(
                    MakeDirActionBlock.model_validate(raw_action)
                )
            except ValidationError as exc:
                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(
                            "Invalid make_dir action: "
                            f"{str(exc)[:120]}"
                        )
                except (AttributeError, TypeError):
                    pass

                raise

        # run_workflow_with_errors is async, so all directory workflows can
        # execute concurrently. gather preserves the input action order.
        results = await asyncio.gather(
            *(_run_one_make_dir(action) for action in actions),
            return_exceptions=True,
        )

        language = (language_hint() or "English").strip() or "English"
        context_chunks: list[str] = []
        had_empty_result = False

        for result in results:
            # gather(return_exceptions=True) may return any BaseException.
            if isinstance(result, BaseException):
                had_empty_result = True

                if isinstance(result, TimeoutError):
                    message = "Make dir operation timed out"
                else:
                    message = (
                        "Make dir workflow crashed: "
                        f"{type(result).__name__}: "
                        f"{str(result)[:120]}"
                    )

                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(message)
                except (AttributeError, TypeError):
                    pass

                continue

            result_text, error_text = result

            if error_text and not result_text:
                had_empty_result = True

                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(
                            f"Make dir error: {error_text[:160]}"
                        )
                except (AttributeError, TypeError):
                    pass

                continue

            if not result_text:
                had_empty_result = True
                continue

            context_chunks.append(
                MAKE_DIR_FOLLOW_UP_PREFIX
                + result_text
                + MAKE_DIR_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            )

        if not context_chunks:
            return _empty_make_dir_contribution(language_hint)

        return FollowUpContribution(
            context_chunks=context_chunks,
            any_empty_tool=had_empty_result,
        )

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Make dir workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_make_dir_follow_up"]
