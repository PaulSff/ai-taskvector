from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    GREP_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.grep.follow_ups import (
    GREP_FOLLOW_UP_PREFIX,
    GREP_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 60.0

type GrepFollowUpResult = FollowUpContribution | BaseException


def _empty_grep_contribution(
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = language_hint()

    chunk = (
        GREP_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + GREP_FOLLOW_UP_SUFFIX.format(
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


def _format_grep_result(grep_output: object) -> str:
    if not isinstance(grep_output, Mapping):
        return ""

    output = grep_output.get("out")
    error = grep_output.get("error")

    result = ""

    if output is not None:
        result = str(output).strip()

    if isinstance(error, Mapping):
        error = error.get("error") or error.get("message")

    if error is not None and str(error).strip():
        error_text = str(error).strip()

        result = (
            f"{result}\nError: {error_text}".strip()
            if result
            else f"Error: {error_text}"
        )

    return result


def _is_current_run(
    ctx: ExecutionFollowUpContext,
) -> bool:
    try:
        return ctx.is_current_run(ctx.token)
    except (AttributeError, TypeError, RuntimeError):
        return False


async def _toast_if_current_run(
    ctx: ExecutionFollowUpContext,
    message: str,
) -> None:
    if not _is_current_run(ctx):
        return

    try:
        await ctx.toast(message)
    except (AttributeError, TypeError, RuntimeError):
        pass


def _set_inline_status(
    ctx: ExecutionFollowUpContext,
    message: str,
) -> None:
    try:
        ctx.set_inline_status(message)
    except (AttributeError, TypeError, RuntimeError):
        pass


async def _run_one_grep_action(
    ctx: ExecutionFollowUpContext,
    raw_action: object,
    *,
    language_hint: LanguageHintGetter,
    notify: bool,
) -> FollowUpContribution:
    """
    Validate and execute one grep action.
    """

    # Local import avoids the action-block/follow-up import cycle.
    from agents.tools.grep.action_block import GrepActionBlock

    try:
        action = GrepActionBlock.model_validate(raw_action)

        payload: JsonValue = TypeAdapter(JsonValue).validate_python(
            action.model_dump(mode="json")
        )

        out, errs = await run_workflow_with_errors(
            GREP_WORKFLOW_PATH,
            initial_inputs={
                "inject_payload": {
                    "template": payload,
                }
            },
            unit_param_overrides=None,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs and notify:
            error_text = _format_workflow_error(errs)

            await _toast_if_current_run(
                ctx,
                f"Grep error: {error_text}",
            )

        grep_output: object = {}

        if isinstance(out, Mapping):
            grep_output = out.get("grep") or {}

        result = _format_grep_result(grep_output)

        if not result.strip():
            return _empty_grep_contribution(language_hint)

        language = language_hint()

        chunk = (
            GREP_FOLLOW_UP_PREFIX
            + result
            + GREP_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=False,
        )

    except TimeoutError:
        if notify:
            await _toast_if_current_run(
                ctx,
                "Grep operation timed out",
            )

        return _empty_grep_contribution(language_hint)

    except ValidationError as exc:
        if notify:
            await _toast_if_current_run(
                ctx,
                "Invalid grep action: "
                f"{str(exc)[:120]}",
            )

        raise

    except (
        AttributeError,
        TypeError,
        KeyError,
        ValueError,
        IndexError,
    ) as exc:
        if notify:
            await _toast_if_current_run(
                ctx,
                "Grep workflow crashed: "
                f"{type(exc).__name__}: {str(exc)[:120]}",
            )

        raise


async def run_grep_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
    notify: bool = True,
) -> FollowUpContribution:
    """
    Execute all grep actions in one ParserOutput concurrently.

    Results preserve the original action order. Individual failures are
    omitted from the combined contribution.
    """

    if notify:
        _set_inline_status(ctx, "Using grep…")

    try:
        grep_actions = po.actions.get_tool_actions("grep")

        if not grep_actions:
            raise ValueError(
                "Grep follow-up was requested, but no grep action was found"
            )

        tasks = [
            asyncio.create_task(
                _run_one_grep_action(
                    ctx,
                    raw_action,
                    language_hint=language_hint,
                    notify=notify,
                )
            )
            for raw_action in grep_actions
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        return combine_grep_follow_up_results(results)

    except TimeoutError:
        if notify:
            await _toast_if_current_run(
                ctx,
                "Grep operation timed out",
            )

        return _empty_grep_contribution(language_hint)

    except (
        AttributeError,
        TypeError,
        KeyError,
        ValueError,
        IndexError,
    ) as exc:
        if notify:
            await _toast_if_current_run(
                ctx,
                "Grep workflow crashed: "
                f"{type(exc).__name__}: {str(exc)[:120]}",
            )

        raise


async def run_grep_follow_ups_concurrently(
    ctx: ExecutionFollowUpContext,
    parser_outputs: Sequence[ParserOutput],
    *,
    language_hint: LanguageHintGetter,
) -> list[GrepFollowUpResult]:
    """
    Execute multiple ParserOutputs concurrently.

    Each ParserOutput may contain one or more grep actions. Since
    run_grep_follow_up() also executes actions concurrently, this supports
    concurrency at both the ParserOutput and action levels.
    """

    if not parser_outputs:
        return []

    _set_inline_status(
        ctx,
        f"Running {len(parser_outputs)} grep searches…",
    )

    tasks = [
        asyncio.create_task(
            run_grep_follow_up(
                ctx,
                parser_output,
                language_hint=language_hint,
                notify=False,
            )
        )
        for parser_output in parser_outputs
    ]

    return list(
        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )
    )


def combine_grep_follow_up_results(
    results: Sequence[GrepFollowUpResult],
) -> FollowUpContribution:
    """
    Combine successful grep results while preserving their original order.

    Failed grep calls are omitted.
    """

    context_chunks: list[str] = []
    any_empty_tool = False

    for result in results:
        if isinstance(result, BaseException):
            continue

        context_chunks.extend(result.context_chunks)
        any_empty_tool = (
            any_empty_tool or result.any_empty_tool
        )

    return FollowUpContribution(
        context_chunks=context_chunks,
        any_empty_tool=any_empty_tool,
    )


__all__ = [
    "combine_grep_follow_up_results",
    "run_grep_follow_up",
    "run_grep_follow_ups_concurrently",
]
