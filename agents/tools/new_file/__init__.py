"""
browse follow-up: create one or more new files concurrently via the
new_file workflow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    NEW_FILE_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.new_file.follow_ups import (
    NEW_FILE_FOLLOW_UP_PREFIX,
    NEW_FILE_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_new_file_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = (hint() or "English").strip() or "English"

    chunk = (
        NEW_FILE_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + NEW_FILE_FOLLOW_UP_SUFFIX.format(
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


def _extract_new_file_result(output: object) -> tuple[str, str]:
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


async def _run_one_new_file(
    action: object,
) -> tuple[str, str | None]:
    """
    Execute one normalized new_file action.

    Returns:
        (result_text, error_message)

    An empty result means the action did not produce usable follow-up text.
    """
    payload: JsonValue = TypeAdapter(JsonValue).validate_python(
        action.model_dump(mode="json")  # type: ignore[union-attr]
    )

    out, errs = await run_workflow_with_errors(
        NEW_FILE_WORKFLOW_PATH,
        initial_inputs={
            "inject_payload": {
                "template": payload,
            }
        },
        format="dict",
        execution_timeout_s=EXECUTION_TIMEOUT_S,
    )

    workflow_error = _format_workflow_error(errs) if errs else None

    new_file_output: object = {}
    if isinstance(out, Mapping):
        new_file_output = out.get("generate_new_file") or {}

    new_file_data, new_file_error = _extract_new_file_result(
        new_file_output
    )

    # Prefer an explicit workflow result error. Otherwise retain the
    # workflow-runner error for notification if the output is empty.
    result = new_file_error or new_file_data

    if result:
        return result, None

    return "", workflow_error or new_file_error


async def run_new_file_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.new_file.action_block import NewFileActionBlock

    try:
        ctx.set_inline_status("Creating files…")
    except (AttributeError, TypeError):
        pass

    try:
        raw_actions = po.actions.get_tool_actions("new_file")

        if not raw_actions:
            raise ValueError(
                "New-file follow-up was requested, but no "
                "new_file action was found"
            )

        # Validate every action before starting any workflow. This prevents
        # some files from being created if a later action is malformed.
        actions = []

        for raw_action in raw_actions:
            try:
                actions.append(
                    NewFileActionBlock.model_validate(raw_action)
                )
            except ValidationError as exc:
                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(
                            "Invalid new_file action: "
                            f"{str(exc)[:120]}"
                        )
                except (AttributeError, TypeError):
                    pass

                raise

        # run_workflow_with_errors is async, so gather can execute all
        # workflow calls concurrently without blocking the event loop.
        results = await asyncio.gather(
            *(_run_one_new_file(action) for action in actions),
            return_exceptions=True,
        )

        language = (language_hint() or "English").strip() or "English"
        context_chunks: list[str] = []
        had_empty_result = False

        for result in results:
            if isinstance(result, BaseException):
                had_empty_result = True

                if isinstance(result, TimeoutError):
                    message = "New file operation timed out"
                else:
                    message = (
                        "New file workflow crashed: "
                        f"{type(result).__name__}: {str(result)[:120]}"
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
                            f"New file error: {error_text[:160]}"
                        )
                except (AttributeError, TypeError):
                    pass

                continue

            if not result_text:
                had_empty_result = True
                continue

            context_chunks.append(
                NEW_FILE_FOLLOW_UP_PREFIX
                + result_text
                + NEW_FILE_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            )

        if not context_chunks:
            return _empty_new_file_contribution(language_hint)

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
                    "New file workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_new_file_follow_up"]
