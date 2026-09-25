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
import concurrent.futures
import re
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

from core.schemas.primitives import Data, Output
from runtime.executor import BackgroundCoro
from units.registry import UnitSpec, register_unit

GREP_INPUT_PORTS = [
    ("in", "Any"),
    ("parser_output", "Any"),
]
GREP_OUTPUT_PORTS = [("out", "Any"), ("error", "str")]


def _clean_str(value: object | None) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()

def _get_timeout(params: Data, default: float = 30.0) -> float:
    value = params.get("timeout")

    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default

    return default

def _normalize_options(value: object) -> list[str]:
    if isinstance(value, str):
        return [
            option.strip()
            for option in value.split()
            if option.strip()
        ]

    if isinstance(value, (list, tuple, set)):
        return [
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        ]

    return []

def _get_background_loop_from_params(
    params: Data,
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
    grep_pattern: str,
    grep_source: str,
    is_file: bool,
    options_list: list[str],
) -> str:
    flags = 0

    if any(option == "-i" for option in options_list):
        flags |= re.IGNORECASE

    try:
        regex = re.compile(grep_pattern, flags)
    except re.error:
        regex = re.compile(re.escape(grep_pattern), flags)

    matches: list[tuple[int, str]] = []

    if is_file:
        try:
            with open(
                grep_source,
                "r",
                encoding="utf-8",
                errors="replace",
            ) as file_handle:
                for line_number, line in enumerate(file_handle, start=1):
                    if regex.search(line):
                        matches.append(
                            (line_number, line.rstrip("\n"))
                        )
        except OSError as exc:
            raise RuntimeError(f"file read failed: {exc}") from exc
    else:
        for line_number, line in enumerate(
            grep_source.splitlines(),
            start=1,
        ):
            if regex.search(line):
                matches.append((line_number, line))

    show_line_numbers = (
        "-n" in options_list
        or "--line-number" in options_list
    )

    output_lines: list[str] = []

    for line_number, line_text in matches:
        if show_line_numbers:
            output_lines.append(f"{line_number}:{line_text}")
        else:
            output_lines.append(line_text)

    return "\n".join(output_lines)


def _schedule_on_background_loop(
    coro: BackgroundCoro,
    background_loop: asyncio.AbstractEventLoop,
    timeout_seconds: float,
) -> tuple[list[float], dict[str, object]]:
    if not background_loop.is_running():
        raise RuntimeError("background loop not running")

    future = asyncio.run_coroutine_threadsafe(
        coro,
        background_loop,
    )

    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeout:
        future.cancel()
        raise TimeoutError("grep timed out")


def _grep_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:

    par = params or {}

    pattern = _clean_str(
        par.get("pattern")
        or par.get("regex")
        or par.get("command")
    )

    source = par.get("source") or par.get("path") or par.get("file")

    parser_output = inputs.get("parser_output") if inputs else None

    if isinstance(parser_output, dict):
        payload: Data | None = None

        nested_payload = parser_output.get("grep")

        if isinstance(nested_payload, dict):
            payload = nested_payload
        elif parser_output.get("action") == "grep":
            payload = parser_output

        if payload is not None:
            pattern = _clean_str(
                payload.get("pattern")
                or payload.get("command")
                or payload.get("regex")
                or pattern
            )

            payload_source = payload.get("source")

            if payload_source is not None:
                source = _clean_str(payload_source)
            elif source is None and inputs:
                source = inputs.get("in")

    if source is None and inputs:
        source = inputs.get("in")

    source_text = _clean_str(source)

    options = par.get("options") or "-n"
    timeout = _get_timeout(par)

    err_msg: str | None = None
    result = ""

    if not pattern or not source_text:
        return ({"out": "", "error": None}, state)

    # Determine whether source is a file path.
    path_obj: Path | None = None

    try:
        path_obj = Path(source_text).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        path_obj = None

    use_file = path_obj is not None and path_obj.is_file()
    opt_list = _normalize_options(options)


    background_loop = _get_background_loop_from_params(par)

    try:
        if (
            isinstance(background_loop, asyncio.AbstractEventLoop)
            and background_loop.is_running()
        ):

            async def _run_on_bg() -> tuple[
                list[float],
                dict[str, object],
            ]:
                loop = asyncio.get_running_loop()

                grep_result = await loop.run_in_executor(
                    None,
                    _python_grep_sync,
                    pattern,
                    str(path_obj) if use_file else source_text,
                    use_file,
                    opt_list,
                )

                # Preserve the core BackgroundCoro result contract.
                return ([], {"out": grep_result})

            try:
                scheduled_result = _schedule_on_background_loop(
                    _run_on_bg(),
                    background_loop,
                    timeout,
                )

                output_value = scheduled_result[1].get("out")

                if isinstance(output_value, str):
                    result = output_value
                else:
                    result = ""

            except TimeoutError:
                err_msg = "grep timed out"
            except (TypeError, ValueError, RuntimeError) as exc:
                err_msg = str(exc)[:200]

        else:
            # Enforce timeout for the synchronous path.
            try:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=1
                ) as executor:
                    future = executor.submit(
                        _python_grep_sync,
                        pattern,
                        str(path_obj) if use_file else source_text,
                        use_file,
                        opt_list,
                    )

                    result = future.result(timeout=timeout) or ""

            except FutureTimeout:
                err_msg = "grep timed out"
            except (TypeError, ValueError, RuntimeError, OSError) as exc:
                err_msg = str(exc)[:200]

    except (TypeError, ValueError, RuntimeError) as exc:
        err_msg = str(exc)[:200]

    return ({"out": result, "error": err_msg}, state)


def register_grep() -> None:
    register_unit(
        UnitSpec(
            type_name="grep",
            input_ports=GREP_INPUT_PORTS,
            output_ports=GREP_OUTPUT_PORTS,
            step_fn=_grep_step,
            environment_tags=["discovery"],
            environment_tags_are_agnostic=False,
            runtime_scope=None,
            description="Grep in a file (path) or raw text using pure Python (no subprocess). Params: pattern/command, source/path (or from input 'in'), options, timeout.",
        )
    )


__all__ = ["GREP_INPUT_PORTS", "GREP_OUTPUT_PORTS", "register_grep"]
