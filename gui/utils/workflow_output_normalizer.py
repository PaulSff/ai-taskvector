"""Normalize merge_response fields from assistant workflows for GUI consumers."""

from __future__ import annotations

import json
from typing import Any


def normalize_follow_up_parser_output(raw_po: Any) -> dict[str, Any]:
    """
    Normalize merge_response.parser_output for the Workflow Designer follow-up chain.

    Aggregate stores missing inputs as ""; some paths may stringify JSON. Callers must not
    treat non-list/non-dict values as fatal: coerce to a dict with an optional "edits" list.
    """
    if raw_po is None or raw_po == "":
        return {"edits": []}
    if isinstance(raw_po, dict):
        return raw_po
    if isinstance(raw_po, list):
        return {"edits": raw_po}
    if isinstance(raw_po, str):
        s = raw_po.strip()
        if not s:
            return {"edits": []}
        try:
            parsed = json.loads(s)
        except Exception:
            return {"edits": []}
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"edits": parsed}
        return {"edits": []}
    return {"edits": []}


def formulas_calc_display_appendix(
    response: dict[str, Any] | None,
    *,
    max_json_chars: int = 8000,
) -> str:
    """
    Markdown appendix for chat: surface ``formulas_calc_output`` / ``formulas_calc_error`` from
    ``run_assistant_workflow`` merge_response so users (and the model in the next bubble) see numbers.
    """
    if not isinstance(response, dict):
        return ""
    raw_out = response.get("formulas_calc_output")
    err_raw = response.get("formulas_calc_error")
    err_s = err_raw.strip() if isinstance(err_raw, str) else ""

    out: Any = raw_out
    if isinstance(out, str) and out.strip():
        try:
            out = json.loads(out)
        except Exception:
            out = {"_raw": out}

    if not err_s and (out is None or out == ""):
        return ""
    if not err_s and isinstance(out, dict) and not out:
        return ""
    if not err_s and isinstance(out, (list, tuple)) and len(out) == 0:
        return ""

    try:
        body = json.dumps(out, indent=2, default=str) if out not in (None, "") else ""
    except TypeError:
        body = str(out)
    if len(body) > max_json_chars:
        body = body[:max_json_chars] + "\n… (truncated)"

    lines = ["", "---", "**Spreadsheet / formula results**"]
    if err_s:
        lines.append(f"*Error:* {err_s}")
    if body.strip():
        lines.append("```json")
        lines.append(body.strip())
        lines.append("```")
    return "\n".join(lines)


def apply_meta_with_formulas_calc_tool_status(
    workflow_response: dict[str, Any] | None,
    apply_meta: Any,
) -> dict[str, Any]:
    """
    When the merge response includes a ``formulas_calc`` parser action but ApplyEdits did not run
    (``attempted`` is not True), surface success/failure in ``apply`` so the chat bubble shows the
    same **Applied** / failed header as graph edits.
    """
    base = dict(apply_meta) if isinstance(apply_meta, dict) else {}
    if base.get("attempted") is True:
        return base
    if not isinstance(workflow_response, dict):
        return base
    po = workflow_response.get("parser_output")
    fc = po.get("formulas_calc") if isinstance(po, dict) else None
    if not isinstance(fc, dict) or fc.get("action") != "formulas_calc":
        return base
    err_raw = workflow_response.get("formulas_calc_error")
    err_s = err_raw.strip() if isinstance(err_raw, str) else ""
    if err_s:
        return {
            **base,
            "attempted": True,
            "success": False,
            "error": err_s,
            "edits_summary": base.get("edits_summary") or "Excel formulas_calc failed",
        }
    return {
        **base,
        "attempted": True,
        "success": True,
        "edits_summary": base.get("edits_summary") or "Excel formulas_calc",
    }
