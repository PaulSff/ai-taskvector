"""
JsonParser unit: parse JSON text into dict/list for downstream RAG / classify / extract.

Params: ``wrap_top_level_list`` (bool) — if true and the root is a JSON array, emit ``{"nodes": <array>}``
so workflow extractors match Node-RED-style shapes.
"""
from __future__ import annotations

import json
from typing import Any

from units.registry import UnitSpec, register_unit

JSON_PARSER_INPUT_PORTS = [("data", "Any")]
JSON_PARSER_OUTPUT_PORTS = [("parsed", "Any"), ("file_path", "str"), ("error", "str")]


def _json_parser_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = inputs.get("data")
    wrap = bool(params.get("wrap_top_level_list"))
    err = ""
    fp_out = ""
    if raw is None:
        return {"parsed": None, "file_path": "", "error": "missing data"}, state
    if isinstance(raw, dict) and "parsed" in raw:
        fp_out = str(raw.get("file_path") or "").strip()
        raw = raw.get("parsed")
        if raw is None:
            return {"parsed": None, "file_path": fp_out, "error": err}, state
    if isinstance(raw, (dict, list)):
        parsed: Any = raw
    elif isinstance(raw, (bytes, bytearray)):
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as e:
            return {"parsed": None, "file_path": fp_out, "error": str(e)}, state
    else:
        s = str(raw).strip()
        if not s:
            return {"parsed": None, "file_path": fp_out, "error": "empty string"}, state
        try:
            parsed = json.loads(s)
        except Exception as e:
            return {"parsed": None, "file_path": fp_out, "error": str(e)}, state

    if wrap and isinstance(parsed, list):
        parsed = {"nodes": parsed}

    return {"parsed": parsed, "file_path": fp_out, "error": err}, state


def register_json_parser() -> None:
    register_unit(
        UnitSpec(
            type_name="JsonParser",
            input_ports=JSON_PARSER_INPUT_PORTS,
            output_ports=JSON_PARSER_OUTPUT_PORTS,
            step_fn=_json_parser_step,
            description="Parse JSON string (or pass through dict/list). Params: wrap_top_level_list.",
        )
    )


__all__ = ["register_json_parser", "JSON_PARSER_INPUT_PORTS", "JSON_PARSER_OUTPUT_PORTS"]
