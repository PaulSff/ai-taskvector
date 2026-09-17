"""
Edit-file follow-up: edit a file via the edit-file workflow.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_edit_file_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Lazy imports avoid the action-block initialization cycle.
    from agents.tools.edit_file.follow_ups import (
        EDIT_FILE_FOLLOW_UP_PREFIX,
        EDIT_FILE_FOLLOW_UP_SUFFIX,
    )
    from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE

    chunk = (
        EDIT_FILE_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + EDIT_FILE_FOLLOW_UP_SUFFIX.format(
            language=hint(),
            session_language=hint(),
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
    )


def _extract_edit_file_result(out: object) -> tuple[str, str]:
    """
    Extract the edit-file workflow result.

    Expected workflow shape:

        {
            "edit_file": {
                "data": "..."
            },
            "error_prompt": {
                "system_prompt": "..."
            }
        }
    """
    if not isinstance(out, Mapping):
        return "", ""

    edit_file_output = out.get("edit_file")
    error_output = out.get("error_prompt")

    data = ""
    error = ""

    if isinstance(edit_file_output, Mapping):
        raw_data = edit_file_output.get("data")

        if isinstance(raw_data, str):
            data = raw_data.strip()
        elif raw_data is not None:
            data = str(raw_data).strip()

    if isinstance(error_output, Mapping):
        raw_error = error_output.get("system_prompt")

        if isinstance(raw_error, str):
            error = raw_error.strip()
        elif raw_error is not None:
            error = str(raw_error).strip()

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


async def run_edit_file_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep application imports local to avoid this cycle:
    #
    # edit_file.__init__
    #   -> action_block
    #   -> follow_ups
    #   -> agent_workflow
    #   -> edit_file package
    from agents.chat.agent_workflow import (
        EDIT_FILE_WORKFLOW_PATH,
        run_workflow_with_errors,
    )
    from agents.tools.edit_file.action_block import EditFileActionBlock
    from agents.tools.edit_file.follow_ups import (
        EDIT_FILE_FOLLOW_UP_PREFIX,
        EDIT_FILE_FOLLOW_UP_SUFFIX,
    )
    from core.schemas.primitives import WorkflowInputs

    try:
        ctx.set_inline_status("Editing file…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        edit_file_actions = po.actions.get_tool_actions("edit_file")

        if not edit_file_actions:
            raise ValueError(
                "Edit-file follow-up was requested, but no "
                "edit_file action was found"
            )

        if len(edit_file_actions) != 1:
            raise ValueError(
                "Edit-file follow-up expected exactly one edit_file action, "
                f"got {len(edit_file_actions)}"
            )

        raw_action = edit_file_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = EditFileActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            raise ValueError(
                "Invalid edit_file action block: "
                f"errors={exc.errors()!r}"
            ) from exc

        # Pass the complete normalized action to the workflow. The workflow
        # needs output_dir, file_name, and the replacement definitions.
        payload = TypeAdapter(JsonValue).validate_json(
            action.model_dump_json()
        )

        initial_inputs: WorkflowInputs = {
            "inject_payload": {
                "template": payload,
            }
        }

        out, errs = await run_workflow_with_errors(
            EDIT_FILE_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Edit file error: {error_text}")
            except (AttributeError, TypeError):
                pass

        edit_file_data, edit_file_error = _extract_edit_file_result(out)

        # Prefer the explicit error prompt from the workflow output.
        result = edit_file_error or edit_file_data

        if not result:
            return _empty_edit_file_contribution(hint)

        chunk = (
            EDIT_FILE_FOLLOW_UP_PREFIX
            + result
            + EDIT_FILE_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=False,
        )

    except TimeoutError:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast("Edit-file operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_edit_file_contribution(hint)

    except ValidationError as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Invalid edit-file action: "
                    f"{str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Edit-file workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_edit_file_follow_up"]
