"""
formulas_calc follow-up: run ``formulas_calc_workflow.json`` (Inject → FormulasCalc) per parser payload.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from assistants.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from assistants.tools.formulas_calc.follow_ups import (
    FORMULAS_CALC_FOLLOW_UP_PREFIX,
    FORMULAS_CALC_FOLLOW_UP_SUFFIX,
)
from assistants.tools.types import FollowUpContribution
from assistants.tools.workflow_path import get_tool_workflow_path


def _format_calc_body(results: Any, err: str | None) -> str:
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


def _coerce_merged_formulas_output(raw: Any) -> Any:
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def _run_formulas_calc_workflow(action: dict[str, Any]) -> str:
    cmd = dict(action)
    cmd.setdefault("action", "formulas_calc")
    if cmd.get("action") != "formulas_calc":
        return ""
    try:
        from runtime.run import run_workflow

        wf = get_tool_workflow_path("formulas_calc")
        if not wf.is_file():
            return ""
        out = run_workflow(
            wf,
            initial_inputs={"inject_formulas_calc": {"data": cmd}},
            format="dict",
        )
        if not isinstance(out, dict):
            return ""
        slot = out.get("formulas_calc")
        if not isinstance(slot, dict):
            return ""
        err = slot.get("error")
        err_s = err.strip() if isinstance(err, str) else ""
        body = _format_calc_body(slot.get("results"), err_s or None)
        return body.strip()
    except Exception:
        return ""


async def run_formulas_calc_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    """
    Build follow-up context from ``formulas_calc`` on parser_output (same shape as the LLM action dict).

    When the assistant workflow already ran FormulasCalc, prefer ``formulas_calc_output`` from
    ``follow_up_source_response`` to avoid duplicate work.
    """
    try:
        setter = getattr(ctx, "set_inline_status", None)
        if callable(setter):
            setter("Excel formulas…")
    except Exception:
        pass
    hint = language_hint
    try:
        wf_resp = getattr(ctx, "follow_up_source_response", None)
        merged_results: Any = None
        merged_err: str = ""
        if isinstance(wf_resp, dict):
            merged_results = _coerce_merged_formulas_output(wf_resp.get("formulas_calc_output"))
            e = wf_resp.get("formulas_calc_error")
            if isinstance(e, str):
                merged_err = e.strip()

        fc = po.get("formulas_calc")
        text = ""
        if merged_err:
            text = _format_calc_body(merged_results, merged_err)
        elif isinstance(merged_results, dict):
            text = _format_calc_body(merged_results, None)
        elif merged_results not in (None, ""):
            text = _format_calc_body(merged_results, None)
        elif isinstance(fc, dict):
            text = await asyncio.to_thread(_run_formulas_calc_workflow, fc)

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
        )
    except Exception:
        chunk = (
            FORMULAS_CALC_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + FORMULAS_CALC_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk], any_empty_tool=True)


__all__ = ["run_formulas_calc_follow_up"]
