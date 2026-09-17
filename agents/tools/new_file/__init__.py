"""
browse follow-up: create new file via new_file workflow.
"""

from __future__ import annotations

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
    language = hint()

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

    data = ""
    error = ""

    if raw_data is not None:
        data = str(raw_data).strip()

    if isinstance(raw_error, Mapping):
        if "error" in raw_error:
            raw_error = raw_error["error"]
        elif "message" in raw_error:
            raw_error = raw_error["message"]

    if raw_error is not None:
        error = str(raw_error).strip()

    return data, error


async def run_new_file_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.new_file.action_block import NewFileActionBlock

    try:
        ctx.set_inline_status("Creating new file…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        new_file_actions = po.actions.get_tool_actions("new_file")

        if not new_file_actions:
            raise ValueError(
                "New-file follow-up was requested, but no "
                "new_file action was found"
            )

        if len(new_file_actions) != 1:
            raise ValueError(
                "New-file follow-up expected exactly one new_file action, "
                f"got {len(new_file_actions)}"
            )

        raw_action = new_file_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = NewFileActionBlock.model_validate(raw_action)
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

        # Pass the complete normalized action to the workflow.
        payload: JsonValue = TypeAdapter(JsonValue).validate_python(
            action.model_dump(mode="json")
        )

        initial_inputs = {
            "inject_payload": {
                "template": payload,
            }
        }

        out, errs = await run_workflow_with_errors(
            NEW_FILE_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"New file error: {error_text}")
            except (AttributeError, TypeError):
                pass

        new_file_output: object = {}

        if isinstance(out, Mapping):
            new_file_output = out.get("generate_new_file") or {}

        new_file_data, new_file_error = _extract_new_file_result(
            new_file_output
        )

        # Prefer an explicit error returned by the workflow.
        result = new_file_error or new_file_data

        if not result:
            return _empty_new_file_contribution(hint)

        language = hint()

        chunk = (
            NEW_FILE_FOLLOW_UP_PREFIX
            + result
            + NEW_FILE_FOLLOW_UP_SUFFIX.format(
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
                await ctx.toast("New file operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_new_file_contribution(hint)

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
