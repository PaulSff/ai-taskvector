"""
Debug unit: forward input to an output port and append a log line to log.txt.

Input: data (Any). Output: data (Any) — pass-through.
Param: log_path (str, optional) — path to log file; default "log.txt".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

DEBUG_INPUT_PORTS = [("data", "Any")]
DEBUG_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _serialize(value: Any) -> str:
    """Convert value to a log-friendly string."""
    if value is None:
        return "(no data received; upstream unit did not produce output or not connected)"
    if isinstance(value, str):
        return value if value.strip() else "(empty)"
    if isinstance(value, dict):
        # If all values are None/empty, summarize as "(no errors)" for error-aggregator logs
        vals = list(value.values()) if value else []
        if all(v is None or (isinstance(v, str) and not (v or "").strip()) for v in vals):
            return "(no errors)"
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return repr(value)
    if isinstance(value, list):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return repr(value)
    return repr(value)


def _debug_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Forward input to output and append a line to log_path."""
    data = inputs.get("data")
    log_path = params.get("log_path") or "log.txt"
    if not isinstance(log_path, str):
        log_path = str(log_path)
    log_path = Path(log_path.strip()).expanduser()
    err: str | None = None
    try:
        line = _serialize(data)
        ts = datetime.now(timezone.utc).isoformat()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {line}\n")
    except OSError as e:
        err = str(e)[:200]
    return ({"data": data, "error": err}, state)


def register_debug() -> None:
    """Register the Debug unit type."""
    register_unit(UnitSpec(
        type_name="Debug",
        input_ports=DEBUG_INPUT_PORTS,
        output_ports=DEBUG_OUTPUT_PORTS,
        step_fn=_debug_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Forward input to output and append the value to log.txt (or log_path param). Params: log_path (optional).",
    ))


__all__ = ["register_debug", "DEBUG_INPUT_PORTS", "DEBUG_OUTPUT_PORTS"]
