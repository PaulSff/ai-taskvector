"""
Delete follow-up: delete a file or folder via the delete workflow.
"""

from __future__ import annotations

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
    # Lazy imports avoid the initialization cycle:
    #
    # delete.__init__
    #   -> action_block
    #   -> follow_ups
    #   -> agent_workflow
    #   -> delete package
    from agents.tools.delete.follow_ups import (
        DELETE_FOLLOW_UP_PREFIX,
        DELETE_FOLLOW_UP_SUFFIX,
    )
    from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE

    chunk = (
        DELETE_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + DELETE_FOLLOW_UP_SUFFIX.format(
            language=hint(),
            session_language=hint(),
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
    )


def _extract_delete_result(out: object) -> tuple[str, str]:
    """
    Extract the delete workflow result.

    Expected workflow shape:

        {
            "delete": {
                "data": "...",
                "error": "..."
            }
        }
    """
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


async def run_delete_file_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Application imports remain local to avoid the action-block import cycle.
    from agents.chat.agent_workflow import (
        DELETE_WORKFLOW_PATH,
        run_workflow_with_errors,
    )
    from agents.tools.delete.action_block import DeleteActionBlock
    from agents.tools.delete.follow_ups import (
        DELETE_FOLLOW_UP_PREFIX,
        DELETE_FOLLOW_UP_SUFFIX,
    )
    from core.schemas.primitives import WorkflowInputs

    try:
        ctx.set_inline_status("Deleting items…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        delete_actions = po.actions.get_tool_actions("delete")

        if not delete_actions:
            raise ValueError(
                "Delete follow-up was requested, but no delete action was found"
            )

        if len(delete_actions) != 1:
            raise ValueError(
                "Delete follow-up expected exactly one delete action, got "
                f"{len(delete_actions)}"
            )

        raw_action = delete_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = DeleteActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            raise ValueError(
                "Invalid delete action block: "
                f"errors={exc.errors()!r}"
            ) from exc

        path = action.path.strip()

        if not path:
            raise ValueError("Delete action path must not be empty")

        print(
            "[run_delete_file_follow_up] "
            f"validated action path={path!r}",
            flush=True,
        )

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

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Delete file error: {error_text}")
            except (AttributeError, TypeError):
                pass

        delete_data, delete_error = _extract_delete_result(out)

        # Prefer the explicit error port from the workflow output.
        result = delete_error or delete_data

        if not result:
            return _empty_delete_contribution(hint)

        chunk = (
            DELETE_FOLLOW_UP_PREFIX
            + result
            + DELETE_FOLLOW_UP_SUFFIX.format(
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
                await ctx.toast("Delete operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_delete_contribution(hint)

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

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
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
