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
