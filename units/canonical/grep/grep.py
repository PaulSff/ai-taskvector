"""
Grep unit: runs grep to search in a file path or in raw text (e.g. Debug logs).

Supports an action-style use: { "action": "grep", "pattern": "...", "source": "path or text" }.
- **source = path**: path to a file (e.g. "workflow.log"); greps that file. Useful for logs written by Debug.
- **source = text**: raw string (e.g. log content or code); greps via stdin. Useful when upstream (e.g. Debug) feeds text.
- **source omitted**: use the unit input "in" as path or text (existing behaviour).

Pattern can come from params.pattern, params.regex, or params.command (alias for agent use).
"""

from __future__ import annotations

import asyncio
import subprocess
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

GREP_INPUT_PORTS = [
    ("in", "Any"),  # optional: path or raw text to search (e.g. from Debug)
    (
        "parser_output",
        "Any",
    ),  # optional: when from ProcessAgent; if key "grep" present, use pattern/source from it
]
GREP_OUTPUT_PORTS = [("out", "Any"), ("error", "str")]


# helper to get background loop from params (same heuristic as RunWorkflow)
def _get_background_loop_from_params(
    params: dict[str, Any],
) -> asyncio.AbstractEventLoop | None:
    bg = params.get("_background_loop") or params.get("_executor_loop")
    if isinstance(bg, asyncio.AbstractEventLoop):
        return bg
    exec_obj = params.get("_executor")
    if exec_obj is not None:
        bg = getattr(exec_obj, "background_loop", None) or getattr(
            exec_obj, "loop", None
        )
        if isinstance(bg, asyncio.AbstractEventLoop):
            return bg
    return None


def _run_grep_sync(args, input_text, timeout):
    out = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (out.stdout or "").strip() or (out.stderr or "").strip()


def _schedule_on_background_loop(coro, background_loop: asyncio.AbstractEventLoop):
    if (
        not isinstance(background_loop, asyncio.AbstractEventLoop)
        or not background_loop.is_running()
    ):
        raise RuntimeError("background loop not running")
    fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
    try:
        return fut.result()
    except FutureTimeout:
        raise subprocess.TimeoutExpired(cmd="grep", timeout=0)
    except RuntimeError:
        raise
    except Exception:
        raise


def _grep_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    par = params or {}
    pattern = par.get("pattern") or par.get("regex") or par.get("command") or ""
    source = par.get("source") or par.get("path") or par.get("file")
    parser_output = inputs.get("parser_output") if inputs else None
    if isinstance(parser_output, dict) and "grep" in parser_output:
        payload = parser_output.get("grep") or {}
        if isinstance(payload, dict):
            pattern = (
                payload.get("pattern")
                or payload.get("command")
                or payload.get("regex")
                or ""
            ).strip() or pattern
            src = payload.get("source")
            if src is not None:
                source = str(src).strip() if isinstance(src, str) else str(src)
            elif source is None and inputs:
                source = inputs.get("in")
    if source is None and inputs:
        source = inputs.get("in")
    if source is not None and not isinstance(source, str):
        source = str(source)
    source = (source or "").strip() if isinstance(source, str) else ""
    options = par.get("options") or "-n"
    timeout = float(par.get("timeout") or 30.0)
    err_msg: str | None = None
    result = ""
    if not pattern:
        return ({"out": "", "error": None}, state)
    if not source:
        return ({"out": "", "error": None}, state)

    path_obj = None
    try:
        path_obj = Path(source).expanduser().resolve() if source else None
    except Exception:
        path_obj = None
    use_file = path_obj is not None and path_obj.is_file()

    opt_list = [
        str(o).strip()
        for o in (
            options.strip().split() if isinstance(options, str) else (options or [])
        )
        if str(o).strip()
    ]

    # Prepare args and input_text
    if use_file:
        args = ["grep"] + opt_list + ["-e", pattern, str(path_obj)]
        input_text = None
    else:
        args = ["grep"] + opt_list + ["-e", pattern]
        input_text = source

    background_loop = _get_background_loop_from_params(par)

    try:
        if (
            isinstance(background_loop, asyncio.AbstractEventLoop)
            and background_loop.is_running()
        ):
            # run subprocess.sync in executor thread on the background loop
            async def _run_on_bg():
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, _run_grep_sync, args, input_text, timeout
                )

            outputs = _schedule_on_background_loop(_run_on_bg(), background_loop)
            result = outputs or ""
        else:
            # run synchronously in current thread
            result = _run_grep_sync(args, input_text, timeout)
    except subprocess.TimeoutExpired:
        err_msg = "grep timed out"
    except FileNotFoundError:
        err_msg = "grep command not found"
    except subprocess.SubprocessError as e:
        err_msg = str(e)[:200]
    except Exception as e:
        err_msg = str(e)[:200]

    return ({"out": result, "error": err_msg}, state)


def register_grep() -> None:
    register_unit(
        UnitSpec(
            type_name="grep",
            input_ports=GREP_INPUT_PORTS,
            output_ports=GREP_OUTPUT_PORTS,
            step_fn=_grep_step,
            environment_tags=["canonical"],
            environment_tags_are_agnostic=True,
            runtime_scope=None,
            description="Grep in a file (path) or raw text (e.g. Debug logs). Params: pattern/command, source/path (or from input 'in'). Output: matching lines; error port on failure.",
        )
    )


__all__ = ["register_grep", "GREP_INPUT_PORTS", "GREP_OUTPUT_PORTS"]
