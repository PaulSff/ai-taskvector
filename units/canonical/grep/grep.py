"""
Grep unit: runs grep to search in a file path or in raw text (e.g. Debug logs).

Supports an action-style use: { "action": "grep", "pattern": "...", "source": "path or text" }.
- **source = path**: path to a file (e.g. "log.txt"); greps that file. Useful for logs written by Debug.
- **source = text**: raw string (e.g. log content or code); greps via stdin. Useful when upstream (e.g. Debug) feeds text.
- **source omitted**: use the unit input "in" as path or text (existing behaviour).

Pattern can come from params.pattern, params.regex, or params.command (alias for agent use).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

GREP_INPUT_PORTS = [("in", "Any")]  # optional: path, or raw text to search (e.g. from Debug)
GREP_OUTPUT_PORTS = [("out", "Any"), ("error", "str")]


def _grep_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    par = params or {}
    pattern = par.get("pattern") or par.get("regex") or par.get("command") or ""
    source = par.get("source") or par.get("path") or par.get("file")
    if source is None and inputs:
        source = next(iter(inputs.values()), None)
    if source is not None and not isinstance(source, str):
        source = str(source)
    source = (source or "").strip() if isinstance(source, str) else ""
    options = par.get("options") or "-n"
    err_msg: str | None = None
    result = ""
    if not pattern:
        return ({"out": "", "error": None}, state)
    if not source:
        return ({"out": "", "error": None}, state)
    # Decide: is source a file path or inline text?
    path_obj = Path(source).expanduser().resolve() if source else None
    use_file = path_obj is not None and path_obj.is_file()
    opt_list = [str(o).strip() for o in (options.strip().split() if isinstance(options, str) else (options or [])) if str(o).strip()]
    try:
        if use_file:
            args = ["grep"] + opt_list + ["-e", pattern, str(path_obj)]
            out = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            result = (out.stdout or "").strip() or (out.stderr or "").strip()
        else:
            # Treat source as raw text; run grep on stdin
            args = ["grep"] + opt_list + ["-e", pattern]
            out = subprocess.run(
                args,
                input=source,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            result = (out.stdout or "").strip() or (out.stderr or "").strip()
    except subprocess.TimeoutExpired:
        err_msg = "grep timed out"
    except FileNotFoundError:
        err_msg = "grep command not found"
    except subprocess.SubprocessError as e:
        err_msg = str(e)[:200]
    return ({"out": result, "error": err_msg}, state)


def register_grep() -> None:
    register_unit(UnitSpec(
        type_name="grep",
        input_ports=GREP_INPUT_PORTS,
        output_ports=GREP_OUTPUT_PORTS,
        step_fn=_grep_step,
        environment_tags=["canonical"],
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Grep in a file (path) or raw text (e.g. Debug logs). Params: pattern/command, source/path (or from input 'in'). Output: matching lines; error port on failure.",
    ))


__all__ = ["register_grep", "GREP_INPUT_PORTS", "GREP_OUTPUT_PORTS"]
