"""Normalize merge_response fields from agent workflows for GUI consumers."""

from __future__ import annotations

import json
from typing import cast

from agents.tools.types import ParserOutput
from core.schemas.primitives import Data


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

    return {"edits": []}
