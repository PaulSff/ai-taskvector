"""Normalize merge_response fields from agent workflows for GUI consumers."""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import cast

from agents.chat.agent_workflow.wf_response_schema import AgentWorkflowResponse
from agents.tools.types import ParserOutput
from core.normalizer.shared import serialize
from core.schemas.primitives import Data, is_json_value, is_string_keyed_dict


def _string_key_dict(value: object) -> Data:
    if not isinstance(value, dict):
        return {}

    raw_dict = cast(dict[object, object], value)
    result: Data = {}

    for key, item in raw_dict.items():
        if isinstance(key, str):
            result[key] = item

    return result


def normalize_follow_up_parser_output(
    raw_po: ParserOutput | list[object] | str | None,
) -> Data:
    if raw_po is None:
        return {"edits": []}

    if isinstance(raw_po, ParserOutput):
        return {"edits": raw_po.actions.edits}

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
            return _string_key_dict(parsed)

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
    response: AgentWorkflowResponse | None,
    *,
    max_json_chars: int = 8000,
) -> str:
    if response is None:
        return ""

    direct_response = response.direct_units_response

    raw_out = direct_response.formulas_calc_output
    err_s = direct_response.formulas_calc_error.strip()

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
    workflow_response: AgentWorkflowResponse | None,
    apply_meta: object,
) -> Data:
    """
    When the merged response includes a ``formulas_calc`` parser action but
    ApplyEdits did not run (``attempted`` is not True), surface success/failure
    in ``apply`` so the chat bubble shows the same Applied/failed header as
    graph edits.
    """
    if is_string_keyed_dict(apply_meta):
        base: dict[str, object] = dict(apply_meta)
    else:
        base = {}

    if base.get("attempted") is True:
        return base

    if workflow_response is None:
        return base

    merged_response = workflow_response.merged_response
    parser_output = merged_response.parser_output

    if not is_string_keyed_dict(parser_output):
        return base

    formulas_calc = parser_output.get("formulas_calc")

    if not is_string_keyed_dict(formulas_calc):
        return base

    if formulas_calc.get("action") != "formulas_calc":
        return base

    err_s = merged_response.formulas_calc_error.strip()

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
