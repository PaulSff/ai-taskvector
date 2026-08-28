"""Normalize merge_response fields from agent workflows for GUI consumers."""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import cast

from core.normalizer.shared import serialize
from core.schemas.primitives import is_json_value, is_string_keyed_dict


def _string_key_dict(
    value: dict[object, object],
) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item

    return result


def normalize_follow_up_parser_output(
    raw_po: object,
) -> dict[str, object]:
    if raw_po is None or raw_po == "":
        return {"edits": []}

    if isinstance(raw_po, dict):
        return _string_key_dict(
            cast(dict[object, object], raw_po)
        )

    if isinstance(raw_po, list):
        return {"edits": raw_po}

    if isinstance(raw_po, str):
        text = raw_po.strip()

        if not text:
            return {"edits": []}

        try:
            parsed = cast(object, json.loads(text))
        except json.JSONDecodeError:
            return {"edits": []}

        if isinstance(parsed, dict):
            return _string_key_dict(
                cast(dict[object, object], parsed)
            )

        if isinstance(parsed, list):
            return {"edits": parsed}

    return {"edits": []}


# ---- START Formulas output normalizer ---
def normalize_formula_output(raw: object) -> object:
    if not isinstance(raw, str) or not raw.strip():
        return raw

    try:
        parsed = cast(object, json.loads(raw))
    except JSONDecodeError:
        return {"_raw": raw}

    if is_json_value(parsed):
        return parsed

    return {"_raw": str(parsed)}


def is_empty_formula_output(value: object) -> bool:
    if value is None or value == "":
        return True

    if isinstance(value, dict):
        return not value

    if isinstance(value, (list, tuple)):
        return not value

    return False


def formulas_calc_display_appendix(
    response: dict[str, object] | None,
    *,
    max_json_chars: int = 8000,
) -> str:
    if not isinstance(response, dict):
        return ""

    raw_out = response.get("formulas_calc_output")
    err_raw = response.get("formulas_calc_error")
    err_s = err_raw.strip() if isinstance(err_raw, str) else ""

    out = normalize_formula_output(raw_out)

    if not err_s and is_empty_formula_output(out):
        return ""

    body = serialize(out)

    if len(body) > max_json_chars:
        body = body[:max_json_chars] + "\n… (truncated)"

    lines = ["", "---", "**Spreadsheet / formula results**"]

    if err_s:
        lines.append(f"*Error:* {err_s}")

    if body.strip():
        lines.extend(("```json", body.strip(), "```"))

    return "\n".join(lines)


def apply_meta_with_formulas_calc_tool_status(
    workflow_response: dict[str, object] | None,
    apply_meta: object,
) -> dict[str, object]:
    """
    When the merge response includes a ``formulas_calc`` parser action but
    ApplyEdits did not run (``attempted`` is not True), surface success/failure
    in ``apply`` so the chat bubble shows the same **Applied** / failed header
    as graph edits.
    """
    if is_string_keyed_dict(apply_meta):
        base: dict[str, object] = dict(apply_meta)
    else:
        base = {}

    if base.get("attempted") is True:
        return base

    if not isinstance(workflow_response, dict):
        return base

    parser_output = workflow_response.get("parser_output")

    if not is_string_keyed_dict(parser_output):
        return base

    formulas_calc = parser_output.get("formulas_calc")

    if not is_string_keyed_dict(formulas_calc):
        return base

    if formulas_calc.get("action") != "formulas_calc":
        return base

    err_raw = workflow_response.get("formulas_calc_error")
    err_s = err_raw.strip() if isinstance(err_raw, str) else ""

    if err_s:
        return {
            **base,
            "attempted": True,
            "success": False,
            "error": err_s,
            "edits_summary": (
                base.get("edits_summary")
                or "Excel formulas_calc failed"
            ),
        }

    return {
        **base,
        "attempted": True,
        "success": True,
        "edits_summary": (
            base.get("edits_summary")
            or "Excel formulas_calc"
        ),
    }
