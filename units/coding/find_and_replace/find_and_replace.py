from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

NEW_FILE_INPUT_PORTS = [("parser_output", "Any")]
NEW_FILE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

DIFF_NEW_LINE_TERMINATOR = "\n"
UNIFIED_DIFF_N_CONTEXT_LINES_AROUND = 3


class FindReplaceError(ValueError):
    pass


def _extract_target_file_and_content(parser_output: Any, output_dir: str) -> tuple[Path, str]:
    """
    Reads original from:
      - file.content if provided, else from disk using output_dir + file.file_name

    Returns (original_path, original_text).
    """
    if not isinstance(parser_output, dict) or parser_output.get("action") != "edit_file":
        raise FindReplaceError('missing or invalid parser_output (expected object with {"action": "edit_file", ...})')

    if not isinstance(output_dir, str) or not output_dir.strip():
        raise FindReplaceError("output_dir must be a non-empty string")

    file_obj = parser_output.get("file")
    if not isinstance(file_obj, dict):
        raise FindReplaceError("file is required in parser_output and must be an object")

    file_name = file_obj.get("file_name")
    if not isinstance(file_name, str) or not file_name.strip():
        raise FindReplaceError("file.file_name must be a non-empty string")

    original_path = Path(output_dir, file_name.strip()).expanduser().resolve()

    content = file_obj.get("content")
    if isinstance(content, str):
        original_text = content
    else:
        if not original_path.exists() or not original_path.is_file():
            raise FindReplaceError(f"original target file does not exist: {original_path}")
        original_text = original_path.read_text(encoding="utf-8")

    return original_path, original_text


def _extract_output_dir(parser_output: Any) -> str:
    if not isinstance(parser_output, dict):
        raise FindReplaceError("parser_output must be an object")
    output_dir = parser_output.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise FindReplaceError("output_dir must be a non-empty string")
    return output_dir.strip()


def _extract_replacements_from_new_shape(parser_output: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extracts:
      [parser_output["file"]["replacement_1"], parser_output["file"]["replacement_2"], ...]
    ordered by numeric suffix.

    Note: replacements are expected under parser_output["file"].
    """
    file_obj = parser_output.get("file")
    if not isinstance(file_obj, dict):
        raise FindReplaceError("file is required in parser_output and must be an object")

    reps: list[tuple[int, dict[str, Any]]] = []

    for k, v in file_obj.items():
        m = re.fullmatch(r"replacement_(\d+)", str(k))
        if not m:
            continue

        idx = int(m.group(1))
        if idx < 1:
            raise FindReplaceError(f"{k} must start at replacement_1 (got {k})")

        if not isinstance(v, dict):
            raise FindReplaceError(f"{k} must be an object")

        reps.append((idx, v))

    if not reps:
        raise FindReplaceError("replacements missing (expected at least replacement_1)")

    reps.sort(key=lambda t: t[0])
    return [v for _, v in reps]


def _count_anchor_line_matches(lines: list[str], anchor: str) -> list[int]:
    """
    Returns indices of lines that contain the anchor substring.
    Matching is done against the full line content using `anchor in line`.
    """
    hits: list[int] = []
    for i, line in enumerate(lines):
        if anchor in line:
            hits.append(i)
    return hits


def _apply_replacements_between_anchor_lines_once(
    text: str,
    replacements: Iterable[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """
    For each replacement:
      - find starting anchor line (substring match) exactly once
      - find ending anchor line (substring match) exactly once
      - ending line must come after starting line
      - replace lines strictly between them with insert_in_between
        (start/end anchor lines are preserved)

    Preserves newline characters from the original file to keep the unified diff valid.
    """
    audit: list[dict[str, Any]] = []
    lines = text.splitlines(keepends=True)

    for rep_index, rep in enumerate(replacements):
        starting_anchor = rep.get("find_starting_anchor_line")
        ending_anchor = rep.get("find_ending_anchor_line")
        insert_in_between = rep.get("insert_in_between")

        if not isinstance(starting_anchor, str):
            raise FindReplaceError(f"replacements[{rep_index}].find_starting_anchor_line must be a string")
        if not isinstance(ending_anchor, str):
            raise FindReplaceError(f"replacements[{rep_index}].find_ending_anchor_line must be a string")
        if not isinstance(insert_in_between, str):
            raise FindReplaceError(f"replacements[{rep_index}].insert_in_between must be a string")

        start_hits = _count_anchor_line_matches(lines, starting_anchor)
        end_hits = _count_anchor_line_matches(lines, ending_anchor)

        if len(start_hits) == 0:
            raise FindReplaceError(f"replacements[{rep_index}] starting anchor not found (0 matches)")
        if len(start_hits) > 1:
            raise FindReplaceError(
                f"replacements[{rep_index}] starting anchor ambiguous (>1 matches): {len(start_hits)}"
            )

        if len(end_hits) == 0:
            raise FindReplaceError(f"replacements[{rep_index}] ending anchor not found (0 matches)")
        if len(end_hits) > 1:
            raise FindReplaceError(
                f"replacements[{rep_index}] ending anchor ambiguous (>1 matches): {len(end_hits)}"
            )

        start_i = start_hits[0]
        end_i = end_hits[0]

        if end_i <= start_i:
            raise FindReplaceError(
                f"replacements[{rep_index}] ending anchor occurs before/at starting anchor "
                f"(start line {start_i}, end line {end_i})"
            )

        before = lines[: start_i + 1]
        after = lines[end_i:]  # includes ending anchor line

        insert_lines = insert_in_between.splitlines(keepends=True)

        lines = before + insert_lines + after

        audit.append(
            {
                "index": rep_index,
                "start_line": start_i,
                "end_line": end_i,
                "insert_lines": len(insert_lines),
            }
        )

    return "".join(lines), audit


def _make_unified_diff(
    original_path: Path,
    original_text: str,
    updated_text: str,
    n: int,
) -> str:
    """
    Generates a unified diff string.
    """
    original_lines = original_text.splitlines(keepends=True)
    updated_lines = updated_text.splitlines(keepends=True)

    fromfile = f"a/{original_path}"
    tofile = f"b/{original_path}"

    diff_lines = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=fromfile,
        tofile=tofile,
        n=n,
        lineterm=DIFF_NEW_LINE_TERMINATOR,
    )
    return "".join(diff_lines)


def _hint_for_message(msg: str) -> str:
    if "starting anchor not found" in msg:
        return "Hint: Update find_starting_anchor_line so its substring matches a line in the original text exactly once."
    if "starting anchor ambiguous" in msg:
        return "Hint: Make find_starting_anchor_line more specific so it matches exactly one line (currently >1)."
    if "ending anchor not found" in msg:
        return "Hint: Update find_ending_anchor_line so its substring matches a line in the original text exactly once."
    if "ending anchor ambiguous" in msg:
        return "Hint: Make find_ending_anchor_line more specific so it matches exactly one line (currently >1)."
    if "ending anchor occurs before/at starting anchor" in msg:
        return "Hint: Ensure the ending anchor appears after the starting anchor in the original file."
    if "replacements missing" in msg:
        return "Hint: Provide parser_output['file']['replacement_1'] (and optionally replacement_2, ...)."
    if "must be a non-negative integer" in msg and "unified_diff_n_context_lines_around" in msg:
        return "Hint: Set params.unified_diff_n_context_lines_around to an integer >= 0."
    if "original target file does not exist" in msg:
        return "Hint: Verify parser_output['output_dir'] and parser_output['file']['file_name'] point to an existing file."
    if "file.file_name must be a non-empty string" in msg:
        return "Hint: Ensure parser_output['file']['file_name'] is a non-empty string."
    if "output_dir must be a non-empty string" in msg:
        return "Hint: Ensure parser_output['output_dir'] is a non-empty string."
    if "parser_output must be an object" in msg or "missing or invalid parser_output" in msg:
        return "Hint: Ensure parser_output is an object containing action='edit_file', output_dir, and file (with file_name, and either content or a resolvable file on disk)."
    if "must be a string" in msg:
        return "Hint: Check that the relevant replacement fields are strings (find_starting_anchor_line, find_ending_anchor_line, insert_in_between)."
    return "Hint: Adjust the anchors/replacements so both anchor substrings match exactly one line each, and the ending anchor is after the starting anchor."


def _build_error_with_context(*, e: Exception, parser_output: Any, stage: str) -> str:
    output_dir = ""
    file_name = ""

    if isinstance(parser_output, dict):
        output_dir_val = parser_output.get("output_dir", "")
        if isinstance(output_dir_val, str):
            output_dir = output_dir_val

        file_obj = parser_output.get("file")
        if isinstance(file_obj, dict):
            file_name_val = file_obj.get("file_name", "")
            if isinstance(file_name_val, str):
                file_name = file_name_val

    msg = str(e)
    ctx = f"Context: stage={stage}; output_dir={output_dir!r}; file_name={file_name!r}"
    hint = _hint_for_message(msg)
    return f"{msg}\n{ctx}\n{hint}"



def _find_and_replace_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Requested output shape:
    # { "output_dir": "...", "file": { ok, file_name, output_format, patch, error, file_preview, audit{...}, } }
    out: dict[str, Any] = {
        "ok": False,
        "patch": "",
        "error": None,
        "file_preview": "",
        "audit": [],
    }

    parser_output = inputs.get("parser_output")
    stage = "init"

    try:
        if not isinstance(parser_output, dict):
            raise FindReplaceError("missing or invalid parser_output (expected an object)")

        stage = "extract_output_dir"
        output_dir = _extract_output_dir(parser_output)

        stage = "extract_target_file_and_content"
        original_path, original_text = _extract_target_file_and_content(parser_output, output_dir)

        stage = "extract_replacements"
        replacements = _extract_replacements_from_new_shape(parser_output)

        stage = "validate_diff_params"
        n = params.get("unified_diff_n_context_lines_around", UNIFIED_DIFF_N_CONTEXT_LINES_AROUND)
        if not isinstance(n, int) or n < 0:
            raise FindReplaceError("params.unified_diff_n_context_lines_around must be a non-negative integer")

        stage = "apply_replacements_and_make_patch"
        updated_text, audit_list = _apply_replacements_between_anchor_lines_once(original_text, replacements)
        patch = _make_unified_diff(original_path, original_text, updated_text, n=n)

        out["ok"] = True
        out["patch"] = patch
        out["file_preview"] = updated_text[:500] + ("..." if len(updated_text) > 500 else "")
        out["audit"] = audit_list

        return (
            {
                "data": {
                    "output_dir": output_dir,
                    "file": {
                        "ok": out["ok"],
                        "file_name": original_path.name,
                        "output_format": original_path.suffix.lstrip("."),
                        "patch": out["patch"],
                        "error": None,
                        "file_preview": out["file_preview"],
                        "audit": out["audit"],
                    },
                },
                "error": None,
            },
            state,
        )

    except (FindReplaceError, OSError, UnicodeDecodeError, ValueError, TypeError) as e:
        out["error"] = _build_error_with_context(e=e, parser_output=parser_output, stage=stage)
        return (
            {
                "data": {
                    "output_dir": _extract_output_dir(parser_output) if isinstance(parser_output, dict) else "",
                    "file": {
                        "ok": False,
                        "file_name": "",
                        "output_format": "",
                        "patch": "",
                        "error": out["error"],
                        "file_preview": "",
                        "audit": [],
                    },
                },
                "error": out["error"],
            },
            state,
        )


def register_find_and_replace_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="FindAndReplace",
            input_ports=NEW_FILE_INPUT_PORTS,
            output_ports=NEW_FILE_OUTPUT_PORTS,
            step_fn=_find_and_replace_step,
            environment_tags=["coding"],
            environment_tags_are_agnostic=False,
            description=(
                "Generates a unified-diff patch by editing the region between two anchor lines. "
                "Input must be parser_output with action='edit_file', output_dir, and file.file_name (or file.content), "
                "plus replacement_1 (and optionally replacement_N) objects with: "
                "{find_starting_anchor_line, find_ending_anchor_line, insert_in_between}. "
                "Each anchor line substring must match exactly once; otherwise the unit fails without producing a patch. "
                "Output shape uses audit as a single dict (so this unit supports exactly one replacement)."
            ),
        )
    )


__all__ = ["NEW_FILE_INPUT_PORTS", "NEW_FILE_OUTPUT_PORTS", "register_find_and_replace_unit"]
