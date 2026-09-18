"""
Delete tool runner: delete one or more files or folders concurrently via the
delete workflow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from pydantic import ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_delete_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Lazy imports avoid the initialization cycle.
    from agents.tools.delete.follow_ups import (
        DELETE_FOLLOW_UP_PREFIX,
        DELETE_FOLLOW_UP_SUFFIX,
    )
    from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE

    language = (hint() or "English").strip() or "English"

    chunk = (
        DELETE_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + DELETE_FOLLOW_UP_SUFFIX.format(
            language=language,
            session_language=language,
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
    )


def _extract_delete_result(out: object) -> tuple[str, str]:
    if not isinstance(out, Mapping):
        return "", ""

    delete_output = out.get("delete")

    if not isinstance(delete_output, Mapping):
        return "", ""

    raw_error = delete_output.get("error")
    raw_data = delete_output.get("data")

    error = (
        raw_error.strip()
        if isinstance(raw_error, str)
        else str(raw_error).strip()
        if raw_error is not None
        else ""
    )

    data = (
        raw_data.strip()
        if isinstance(raw_data, str)
        else str(raw_data).strip()
        if raw_data is not None
        else ""
    )

    return data, error


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


async def _run_one_delete(
    path: str,
) -> tuple[str, str | None]:
    """Run one delete workflow for a validated path."""

    from agents.chat.agent_workflow import (
        DELETE_WORKFLOW_PATH,
        run_workflow_with_errors,
    )
    from core.schemas.primitives import WorkflowInputs

    initial_inputs: WorkflowInputs = {
        "inject_payload": {
            "template": path,
        }
    }

    out, errs = await run_workflow_with_errors(
        DELETE_WORKFLOW_PATH,
        initial_inputs=initial_inputs,
        format="dict",
        execution_timeout_s=EXECUTION_TIMEOUT_S,
    )

    workflow_error = _format_workflow_error(errs) if errs else None

    delete_data, delete_error = _extract_delete_result(out)

    # Preserve the original behavior: the explicit workflow error takes
    # precedence over normal workflow data.
    result = delete_error or delete_data

    if result:
        return result, None

    return "", workflow_error or delete_error


async def run_delete_file_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Application imports remain local to avoid import cycles.
    from agents.tools.delete.action_block import DeleteActionBlock
    from agents.tools.delete.follow_ups import (
        DELETE_FOLLOW_UP_PREFIX,
        DELETE_FOLLOW_UP_SUFFIX,
    )

    try:
        ctx.set_inline_status("Deleting items…")
    except (AttributeError, TypeError):
        pass

    try:
        raw_actions = po.actions.get_tool_actions("delete")

        if not raw_actions:
            raise ValueError(
                "Delete follow-up was requested, but no delete action was found"
            )

        # Validate every action before deleting anything. This prevents a
        # malformed later action from causing only partial validation.
        paths: list[str] = []

        for raw_action in raw_actions:
            try:
                action = DeleteActionBlock.model_validate(raw_action)
            except ValidationError as exc:
                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(
                            "Invalid delete action: "
                            f"{str(exc)[:120]}"
                        )
                except (AttributeError, TypeError):
                    pass

                raise

            path = action.path.strip()

            if not path:
                raise ValueError("Delete action path must not be empty")

            paths.append(path)

        # Delete workflows are async, so they can run concurrently. Results
        # remain aligned with paths because gather preserves input ordering.
        results = await asyncio.gather(
            *(_run_one_delete(path) for path in paths),
            return_exceptions=True,
        )

        language = (language_hint() or "English").strip() or "English"
        context_chunks: list[str] = []
        had_empty_result = False

        for result in results:
            if isinstance(result, BaseException):
                had_empty_result = True

                if isinstance(result, TimeoutError):
                    message = "Delete operation timed out"
                else:
                    message = (
                        "Delete workflow crashed: "
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
                            f"Delete file error: {error_text[:160]}"
                        )
                except (AttributeError, TypeError):
                    pass

                continue

            if not result_text:
                had_empty_result = True
                continue

            context_chunks.append(
                DELETE_FOLLOW_UP_PREFIX
                + result_text
                + DELETE_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            )

        if not context_chunks:
            return _empty_delete_contribution(language_hint)

        return FollowUpContribution(
            context_chunks=context_chunks,
            any_empty_tool=had_empty_result,
        )

    except ValidationError:
        raise

    except (
        AttributeError,
        TypeError,
        KeyError,
        ValueError,
        IndexError,
    ) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Delete workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_delete_file_follow_up"]
