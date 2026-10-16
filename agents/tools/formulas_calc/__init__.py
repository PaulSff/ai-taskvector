from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.formulas_calc.follow_ups import (
    FORMULAS_CALC_FOLLOW_UP_PREFIX,
    FORMULAS_CALC_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP,
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)
from agents.tools.workflow_path import get_tool_workflow_path
from core.schemas.primitives import (
    JsonObject,
    WorkflowInputs,
    require_json_object_from_object,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _format_calc_body(results: object, err: str | None) -> str:
    if isinstance(err, str) and err.strip():
        return f"Error: {err.strip()}"

    if results is None or results == "":
        return ""

    if isinstance(results, dict) and not results:
        return "(No output cell values returned; check output ranges and path.)"

    try:
        return json.dumps(results, indent=2, default=str)
    except TypeError:
        return str(results)


def _coerce_merged_formulas_output(raw: object) -> object:
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    return raw


def _format_workflow_error(errs: object) -> str:
    if not errs:
        return "unknown workflow error"

    try:
        first_error = errs[0]  # type: ignore[index]
    except (IndexError, TypeError):
        return str(errs).strip()

    if isinstance(first_error, (tuple, list)) and len(first_error) > 1:
        return str(first_error[1]).strip()

    return str(first_error).strip()


async def _run_formulas_calc_workflow(action: JsonObject) -> str:
    """Execute a validated formulas_calc action."""
    from agents.chat.agent_workflow import run_workflow_with_errors

    command = dict(action)
    command.setdefault("action", "formulas_calc")

    if command.get("action") != "formulas_calc":
        raise ValueError(
            f"Unsupported formulas_calc command: {command.get('action')!r}"
        )

    workflow_path = get_tool_workflow_path("formulas_calc")

    if not workflow_path.is_file():
        raise FileNotFoundError(
            f"Formulas-calc workflow not found: {workflow_path}"
        )

    command_json = require_json_object_from_object(
        command,
        field="formulas_calc command",
    )

    initial_inputs: WorkflowInputs = {
        "inject_formulas_calc": {
            "template": command_json,
        }
    }

    out, errs = await run_workflow_with_errors(
        workflow_path,
        initial_inputs=initial_inputs,
        format="dict",
        execution_timeout_s=EXECUTION_TIMEOUT_S,
    )

    if errs:
        raise RuntimeError(
            f"Formulas-calc workflow failed: {_format_workflow_error(errs)}"
        )

    if not isinstance(out, Mapping):
        raise TypeError(
            f"Expected mapping from formulas-calc workflow, got {type(out).__name__}"
        )

    slot = out.get("formulas_calc")

    if not isinstance(slot, Mapping):
        raise KeyError("Workflow output is missing the 'formulas_calc' mapping")

    raw_error = slot.get("error")
    if isinstance(raw_error, str) and raw_error.strip():
        return _format_calc_body(slot.get("results"), raw_error)

    return _format_calc_body(slot.get("results"), None)


def _empty_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    chunk = (
        FORMULAS_CALC_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + FORMULAS_CALC_FOLLOW_UP_SUFFIX.format(
            language=hint(),
            session_language=hint(),
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
        extra={
            FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP: True,
        },
    )

def _error_contribution(
    hint: LanguageHintGetter,
    message: str,
) -> FollowUpContribution:
    chunk = (
        FORMULAS_CALC_FOLLOW_UP_PREFIX
        + f"Error: {message}"
        + FORMULAS_CALC_FOLLOW_UP_SUFFIX.format(
            language=hint(),
            session_language=hint(),
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=False,
        extra={
            FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP: True,
        },
    )


async def run_formulas_calc_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    try:
        setter = getattr(ctx, "set_inline_status", None)
        if callable(setter):
            setter("Excel formulas…")
    except (AttributeError, RuntimeError, TypeError):
        pass

    hint = language_hint

    try:
        # Local import avoids the action-block initialization cycle.
        from agents.tools.formulas_calc.action_block import (
            FormulasCalcActionBlock,
        )

        workflow_response = getattr(
            ctx,
            "follow_up_source_response",
            None,
        )

        merged_results: Any = None
        merged_error = ""

        if isinstance(workflow_response, Mapping):
            merged_results = _coerce_merged_formulas_output(
                workflow_response.get("formulas_calc_output")
            )

            raw_error = workflow_response.get("formulas_calc_error")
            if isinstance(raw_error, str):
                merged_error = raw_error.strip()

        # Reuse results from the original workflow when present.
        if merged_error:
            text = _format_calc_body(merged_results, merged_error)
        elif isinstance(merged_results, dict) or merged_results not in (None, ""):
            text = _format_calc_body(merged_results, None)
        else:
            actions = po.actions.get_tool_actions("formulas_calc")

            if len(actions) != 1:
                raise ValueError(
                    "Formulas-calc follow-up expected exactly one "
                    f"formulas_calc action, got {len(actions)}"
                )

            try:
                action_block = FormulasCalcActionBlock.model_validate(
                    actions[0]
                )
            except ValidationError as exc:
                raise ValueError(
                    "Invalid formulas_calc action block: "
                    f"errors={exc.errors()!r}"
                ) from exc

            # Pass a normalized JSON payload to the workflow.
            payload = TypeAdapter(JsonValue).validate_json(
                action_block.model_dump_json()
            )
            action = require_json_object_from_object(
                payload,
                field="formulas_calc action",
            )

            text = await _run_formulas_calc_workflow(action)

        if not text:
            return _empty_contribution(hint)

        chunk = (
            FORMULAS_CALC_FOLLOW_UP_PREFIX
            + text
            + FORMULAS_CALC_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=False,
            extra={
                FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP: True,
            },
        )

    except TimeoutError:
        message = "Formulas-calc operation timed out"

        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast("Excel formulas operation timed out")
        except (AttributeError, RuntimeError, TypeError):
            pass

        return _error_contribution(hint, message)

    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        OSError,
    ) as exc:
        message = f"{type(exc).__name__}: {exc}"

        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(f"Excel formulas error: {message[:120]}")
        except (AttributeError, RuntimeError, TypeError):
            pass

        return _error_contribution(hint, message)


__all__ = ["run_formulas_calc_follow_up"]
