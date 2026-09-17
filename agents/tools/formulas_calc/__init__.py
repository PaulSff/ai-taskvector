from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

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
    Data,
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
        return ""

    try:
        first_error = errs[0]  # type: ignore[index]
    except (IndexError, TypeError):
        return str(errs).strip()

    if isinstance(first_error, (tuple, list)) and len(first_error) > 1:
        return str(first_error[1]).strip()

    return str(first_error).strip()


async def _run_formulas_calc_workflow(
    action: Data,
) -> str:
    """
    Execute the validated formulas_calc action.

    Expected action shape:

        {
            "action": "formulas_calc",
            "method": "calculate",
            "path": "...xlsx",
            "inputs": {...},
            "outputs": ["..."],
            "output_format": "json"
        }
    """
    from agents.chat.agent_workflow import run_workflow_with_errors

    command = dict(action)
    command.setdefault("action", "formulas_calc")

    if command.get("action") != "formulas_calc":
        return ""

    try:
        workflow_path = get_tool_workflow_path("formulas_calc")

        if not workflow_path.is_file():
            return ""

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


        if not isinstance(out, Mapping):
            return ""

        slot = out.get("formulas_calc")

        if not isinstance(slot, Mapping):
            return ""

        raw_error = slot.get("error")
        slot_error = (
            raw_error.strip()
            if isinstance(raw_error, str)
            else ""
        )

        if not slot_error:
            slot_error = _format_workflow_error(errs)

        body = _format_calc_body(
            slot.get("results"),
            slot_error or None,
        )

        return body.strip()

    except (RuntimeError, TypeError):
        # This helper intentionally preserves the previous behavior:
        # workflow failures become an empty follow-up result.
        return ""


async def run_formulas_calc_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """
    Build follow-up context from a formulas_calc action.

    If the original workflow already returned formulas_calc_output,
    reuse it instead of executing the workflow a second time.
    """
    try:
        setter = getattr(ctx, "set_inline_status", None)

        if callable(setter):
            setter("Excel formulas…")
    except RuntimeError:
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

        formulas_calc_actions = po.actions.get_tool_actions(
            "formulas_calc"
        )

        text = ""

        if merged_error:
            text = _format_calc_body(
                merged_results,
                merged_error,
            )

        elif isinstance(merged_results, dict) or (
            merged_results not in (None, "")
        ):
            text = _format_calc_body(
                merged_results,
                None,
            )

        elif formulas_calc_actions:
            if len(formulas_calc_actions) != 1:
                raise ValueError(
                    "Formulas-calc follow-up expected exactly one "
                    "formulas_calc action, got "
                    f"{len(formulas_calc_actions)}"
                )

            raw_action = formulas_calc_actions[0]

            try:
                action_block = FormulasCalcActionBlock.model_validate(
                    raw_action
                )
            except ValidationError as exc:
                raise ValueError(
                    "Invalid formulas_calc action block: "
                    f"errors={exc.errors()!r}"
                ) from exc

            # as_json_object() returns the complete normalized action:
            #
            # {
            #     "action": "formulas_calc",
            #     "method": "calculate",
            #     "path": "...",
            #     "inputs": {...},
            #     "outputs": [...],
            #     "output_format": "json",
            # }
            action = action_block.as_json_object()

            text = await _run_formulas_calc_workflow(action)

        body = text if text else TOOL_EMPTY_RESULT_LINE

        chunk = (
            FORMULAS_CALC_FOLLOW_UP_PREFIX
            + body
            + FORMULAS_CALC_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=not bool(text),
            extra={
                FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP: True,
            },
        )

    except (RuntimeError, TypeError):
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


__all__ = ["run_formulas_calc_follow_up"]
