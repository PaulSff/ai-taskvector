"""
Report follow-up: execute the report workflow and summarize its result.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

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
from agents.tools.workflow_path import get_tool_workflow_path
from core.schemas.primitives import WorkflowInputs
from services.logging import setup_colored_logging

EXECUTION_TIMEOUT_S: float = 30.0

logger = setup_colored_logging(logging.DEBUG)


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


def _extract_report_result(out: object) -> tuple[str, str]:
    """
    Extract the report workflow result.

    Expected workflow shape:

        {
            "generate_file": {
                "data": "...",
                "error": "..."
            }
        }

    ``data`` and ``error`` may be strings or other values that can be
    converted to strings.
    """
    if not isinstance(out, Mapping):
        logger.warning(
            "Report workflow returned no mapping output; type=%s",
            type(out).__name__,
        )
        return "", "Report workflow returned no output"

    generate_file_output = out.get("generate_file")

    if not isinstance(generate_file_output, Mapping):
        logger.warning(
            "Report workflow returned no generate_file output; keys=%s",
            list(out.keys()),
        )
        return "", "Report workflow returned no generate_file output"

    raw_error = generate_file_output.get("error")

    if isinstance(raw_error, str):
        error = raw_error.strip()
    elif raw_error is not None:
        error = str(raw_error).strip()
    else:
        error = ""

    if error:
        logger.error(
            "Report workflow generate_file returned an error: %s",
            error,
        )
        return "", error

    raw_data = generate_file_output.get("data")

    if isinstance(raw_data, str):
        data = raw_data.strip()
    elif raw_data is not None:
        data = str(raw_data).strip()
    else:
        data = ""

    if not data:
        logger.warning(
            "Report workflow generate_file returned no data; keys=%s",
            list(generate_file_output.keys()),
        )
        return "", "Report workflow returned no report data"

    logger.info(
        "Report workflow completed successfully; data_length=%d",
        len(data),
    )

    return data, ""


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


async def run_report_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep these imports local to avoid the action-block/workflow import cycle.
    from agents.chat.agent_workflow import run_workflow_with_errors
    from agents.tools.report.action_block import ReportActionBlock

    try:
        ctx.set_inline_status("Generating a file…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        report_actions = po.actions.get_tool_actions("report")

        if not report_actions:
            raise ValueError(
                "Report follow-up was requested, but no report action was found"
            )

        # We support multiple concurrent report actions.

        async def execute_single_report(raw_act):
            try:
                # Validate and normalize
                action = ReportActionBlock.model_validate(raw_act)
                payload = TypeAdapter(JsonValue).validate_json(
                    action.model_dump_json()
                )

                initial_inputs: WorkflowInputs = {
                    "inject_action": {"template": payload}
                }

                report_workflow_path = get_tool_workflow_path("report")
                out, errs = await run_workflow_with_errors(
                    report_workflow_path,
                    initial_inputs=initial_inputs,
                    format="dict",
                    execution_timeout_s=EXECUTION_TIMEOUT_S,
                )

                workflow_error = _format_workflow_error(errs) if errs else ""
                report_data, report_error = _extract_report_result(out)

                return {
                    "ok": not bool(report_error or workflow_error),
                    "data": report_data,
                    "error": report_error or workflow_error,
                    "converted": False,
                }

            except (TypeError, ValueError, KeyError, AttributeError) as e:
                logger.error("Single report action failed: %s", e)
                return {
                    "ok": False,
                    "data": "",
                    "error": str(e),
                    "converted": True,
                }


        # Execute all actions concurrently
        results = await asyncio.gather(*[execute_single_report(ra) for ra in report_actions])

        # Filter out empty results and join them
        valid_results = []
        for r in results:
            if r["ok"] and r["data"]:
                valid_results.append(r["data"])
            elif r["error"]:
                valid_results.append(r["error"])

        result = "\n\n".join(valid_results)

        if not result:
            return _empty_report_contribution(hint)

        language = hint()

        chunk = (
            REPORT_FOLLOW_UP_PREFIX
            + result
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

    except TimeoutError:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast("Report operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_report_contribution(hint)

    except ValidationError as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Invalid report action: "
                    f"{str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Report workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise

__all__ = ["run_report_follow_up"]
