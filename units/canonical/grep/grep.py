"""
Grep unit: runs the grep command to search in files or input.

Reads from a file path (params.path or params.file) or from the first input (e.g. upstream
provides a path). Output is the matching lines. Env-agnostic; useful for scanning logs or
any text source in our runtime.
"""
from __future__ import annotations

import subprocess
from typing import Any

from units.registry import UnitSpec, register_unit

GREP_INPUT_PORTS = [("in", "Any")]  # optional: path or stream
GREP_OUTPUT_PORTS = [("out", "Any")]


def _grep_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    pattern = (params or {}).get("pattern") or (params or {}).get("regex") or ""
    path = (params or {}).get("path") or (params or {}).get("file")
    if not path and inputs:
        path = next(iter(inputs.values()), None)
    options = (params or {}).get("options") or "-n"  # default: line numbers
    if not pattern:
        return ({"out": ""}, state)
    if not path:
        return ({"out": ""}, state)  # no path: nothing to grep
    opt_list = [str(o).strip() for o in (options.strip().split() if isinstance(options, str) else (options or [])) if str(o).strip()]
    args = ["grep"] + opt_list + ["-e", pattern, str(path)]
    try:
        out = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30.0,
        )
        result = (out.stdout or "").strip() or (out.stderr or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        result = ""
    return ({"out": result}, state)


def register_grep() -> None:
    register_unit(UnitSpec(
        type_name="grep",
        input_ports=GREP_INPUT_PORTS,
        output_ports=GREP_OUTPUT_PORTS,
        step_fn=_grep_step,
        environment_tags=["canonical"],
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Runs grep on a file or path: params pattern (required), path/file (or from input); output is matching lines.",
    ))


__all__ = ["register_grep", "GREP_INPUT_PORTS", "GREP_OUTPUT_PORTS"]
