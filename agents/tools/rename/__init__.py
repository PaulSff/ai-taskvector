"""
rename follow-up: rename item via rename workflow.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    RENAME_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.rename.follow_ups import (
    RENAME_FOLLOW_UP_PREFIX,
    RENAME_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)
from core.schemas.primitives import WorkflowInputs

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_rename_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = hint()

    chunk = (
        RENAME_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + RENAME_FOLLOW_UP_SUFFIX.format(
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


def _extract_result(output: object) -> tuple[str, str]:
    if not isinstance(output, Mapping):
        return "", ""

    raw_data = output.get("data")
    raw_error = output.get("error")

    data = str(raw_data).strip() if raw_data is not None else ""

    if isinstance(raw_error, Mapping):
        if "error" in raw_error:
            raw_error = raw_error["error"]
        elif "message" in raw_error:
            raw_error = raw_error["message"]

    error = str(raw_error).strip() if raw_error is not None else ""

    return data, error


async def run_rename_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.rename.action_block import RenameActionBlock

    try:
        ctx.set_inline_status("Renaming item…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        rename_actions = po.actions.get_tool_actions("rename")

        if not rename_actions:
            raise ValueError(
                "Rename follow-up was requested, but no rename action was found"
            )

        if len(rename_actions) != 1:
            raise ValueError(
                "Rename follow-up expected exactly one rename action, "
                f"got {len(rename_actions)}"
            )

        raw_action = rename_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = RenameActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(
                        "Invalid rename action: "
                        f"{str(exc)[:120]}"
                    )
            except (AttributeError, TypeError):
                pass

            raise

        payload: JsonValue = TypeAdapter(JsonValue).validate_python(
            action.model_dump(mode="json")
        )

        initial_inputs: WorkflowInputs = {
            "inject_payload": {
                "template": [payload],
            }
        }

        out, errs = await run_workflow_with_errors(
            RENAME_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Rename error: {error_text}")
            except (AttributeError, TypeError):
                pass

        rename_output: object = {}

        if isinstance(out, Mapping):
            rename_output = out.get("rename") or {}

        result_data, result_error = _extract_result(rename_output)

        # Prefer an explicit error returned by the workflow.
        result = result_error or result_data

        if not result:
            return _empty_rename_contribution(hint)

        language = hint()

        chunk = (
            RENAME_FOLLOW_UP_PREFIX
            + result
            + RENAME_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=False,
        )

    except TimeoutError:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast("Rename operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_rename_contribution(hint)

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Rename workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_rename_follow_up"]
