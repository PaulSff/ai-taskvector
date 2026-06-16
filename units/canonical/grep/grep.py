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
import re
import subprocess
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

GREP_INPUT_PORTS = [
    ("in", "Any"),
    ("parser_output", "Any"),
]
GREP_OUTPUT_PORTS = [("out", "Any"), ("error", "str")]


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


def _python_grep_sync(
    pattern: str, source: str, use_file: bool, options: list[str]
) -> str:
    """Perform grep-like search in Python and return matching lines joined with newlines.
    Options handling: supports '-n' (line numbers) and '-i' (ignore case) and basic flags in options list."""
    flags = 0
    if any(opt == "-i" for opt in options):
        flags |= re.IGNORECASE

    # Interpret pattern literally unless options include '-E' (extended) or pattern looks like regex.
    # We'll treat pattern as a regex by default to preserve grep flexibility.
    try:
        regex = re.compile(pattern, flags)
    except re.error:
        # Fallback: escape pattern
        regex = re.compile(re.escape(pattern), flags)

    lines = []
    if use_file:
        try:
            with open(source, "r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if regex.search(line):
                        lines.append((lineno, line.rstrip("\n")))
        except Exception as e:
            raise RuntimeError(f"file read failed: {e}") from e
    else:
        for lineno, line in enumerate(source.splitlines(), start=1):
            if regex.search(line):
                lines.append((lineno, line))

    show_lineno = any(opt == "-n" for opt in options) or any(
        opt == "--line-number" for opt in options
    )
    joined = []
    for ln, text in lines:
        if show_lineno:
            joined.append(f"{ln}:{text}")
        else:
            joined.append(text)
    return "\n".join(joined)


def _schedule_on_background_loop(
    coro: Any, background_loop: asyncio.AbstractEventLoop, timeout: float
) -> Any:
    if (
        not isinstance(background_loop, asyncio.AbstractEventLoop)
        or not background_loop.is_running()
    ):
        raise RuntimeError("background loop not running")
    fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
    try:
        return fut.result(timeout=timeout)
    except FutureTimeout:
        fut.cancel()
        raise subprocess.TimeoutExpired(cmd="grep", timeout=timeout)
    except Exception:
        raise


def _grep_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import asyncio
    import concurrent.futures
    from concurrent.futures import TimeoutError as FutureTimeout

    par = params or {}
    pattern = (
        par.get("pattern") or par.get("regex") or par.get("command") or ""
    ).strip()
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

    # Determine if source is file path
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

    # Pure-Python grep implementation
    def _python_grep_sync(
        pattern: str, source_text: str, is_file: bool, options_list: list[str]
    ) -> str:
        import re

        flags = 0
        if any(opt == "-i" for opt in options_list):
            flags |= re.IGNORECASE

        try:
            regex = re.compile(pattern, flags)
        except re.error:
            regex = re.compile(re.escape(pattern), flags)

        matches: list[tuple[int, str]] = []
        if is_file:
            try:
                with open(source_text, "r", encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        if regex.search(line):
                            matches.append((lineno, line.rstrip("\n")))
            except Exception as e:
                raise RuntimeError(f"file read failed: {e}") from e
        else:
            for lineno, line in enumerate(source_text.splitlines(), start=1):
                if regex.search(line):
                    matches.append((lineno, line))

        show_lineno = any(opt == "-n" for opt in options_list) or any(
            opt == "--line-number" for opt in options_list
        )
        out_lines = []
        for ln, text in matches:
            if show_lineno:
                out_lines.append(f"{ln}:{text}")
            else:
                out_lines.append(text)
        return "\n".join(out_lines)

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

    def _schedule_on_background_loop(
        coro: Any, background_loop: asyncio.AbstractEventLoop, timeout_s: float
    ) -> Any:
        if (
            not isinstance(background_loop, asyncio.AbstractEventLoop)
            or not background_loop.is_running()
        ):
            raise RuntimeError("background loop not running")
        fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
        try:
            return fut.result(timeout=timeout_s)
        except FutureTimeout:
            try:
                fut.cancel()
            except Exception:
                pass
            raise TimeoutError("grep timed out")
        except Exception:
            raise

    background_loop = _get_background_loop_from_params(par)

    try:
        if (
            isinstance(background_loop, asyncio.AbstractEventLoop)
            and background_loop.is_running()
        ):

            async def _run_on_bg():
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None,
                    _python_grep_sync,
                    pattern,
                    str(path_obj) if use_file else source,
                    use_file,
                    opt_list,
                )

            try:
                result = (
                    _schedule_on_background_loop(_run_on_bg(), background_loop, timeout)
                    or ""
                )
            except TimeoutError:
                err_msg = "grep timed out"
            except Exception as e:
                err_msg = str(e)[:200]
        else:
            # Enforce timeout for synchronous path by using a temporary ThreadPoolExecutor
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(
                        _python_grep_sync,
                        pattern,
                        str(path_obj) if use_file else source,
                        use_file,
                        opt_list,
                    )
                    result = fut.result(timeout=timeout) or ""
            except FutureTimeout:
                err_msg = "grep timed out"
            except Exception as e:
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
            description="Grep in a file (path) or raw text using pure Python (no subprocess). Params: pattern/command, source/path (or from input 'in'), options, timeout.",
        )
    )


__all__ = ["register_grep", "GREP_INPUT_PORTS", "GREP_OUTPUT_PORTS"]
