"""
FindAndReplace Unit API:
{
  "action": "edit_file",
  "output_dir": "path/to/my",
  "file": {
    "file_name": "example.py",
    "replacement_1": {
      "line_num_ref": 126,
      "find": "old text",
      "replace_with": "new text"
    }
  }
}
- replace_with: "" - use empty string to delete text selected
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict, cast

from units.registry import UnitSpec, register_unit

NEW_FILE_INPUT_PORTS = [("parser_output", "Any")]
NEW_FILE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

DIFF_NEW_LINE_TERMINATOR = "\n"
UNIFIED_DIFF_N_CONTEXT_LINES_AROUND = 3


class FindReplaceError(ValueError):
    pass


def _extract_output_dir(parser_output: object) -> str:
    if not isinstance(parser_output, dict):
        raise FindReplaceError("parser_output must be an object")

    parsed = cast(dict[str, object], parser_output)
    output_dir = parsed.get("output_dir")

    if not isinstance(output_dir, str) or not output_dir.strip():
        raise FindReplaceError("output_dir must be a non-empty string")

    return output_dir.strip()


def _extract_target_file_and_content(
    parser_output: object,
    output_dir: str,
) -> tuple[Path, str]:
    """
    Reads the original file from:

      - file.content, if provided
      - otherwise output_dir / file.file_name

    Returns:
        (original_path, original_text)
    """
    if not isinstance(parser_output, dict):
        raise FindReplaceError(
            "missing or invalid parser_output (expected object with action='edit_file')"
        )

    parser_output = cast(dict[str, object], parser_output)

    if parser_output.get("action") != "edit_file":
        raise FindReplaceError(
            "missing or invalid parser_output (expected object with action='edit_file')"
        )

    file_obj = parser_output.get("file")
    if not isinstance(file_obj, dict):
        raise FindReplaceError(
            "file is required in parser_output and must be an object"
        )

    file_obj = cast(dict[str, object], file_obj)
    file_name = file_obj.get("file_name")

    if not isinstance(file_name, str) or not file_name.strip():
        raise FindReplaceError(
            "file.file_name must be a non-empty string"
        )

    output_dir_path = Path(output_dir).expanduser().resolve()
    original_path = (output_dir_path / file_name.strip()).resolve()

    # Prevent file_name values such as ../other_file.py from escaping output_dir.
    file_name = file_obj.get("file_name")

    if not isinstance(file_name, str) or not file_name.strip():
        raise FindReplaceError(
            "file.file_name must be a non-empty string"
        )

    content = file_obj.get("content")

    if isinstance(content, str):
        original_text = content
    else:
        if not original_path.exists() or not original_path.is_file():
            raise FindReplaceError(
                f"original target file does not exist: {original_path}"
            )

        original_text = original_path.read_text(encoding="utf-8")

    return original_path, original_text


def _extract_replacements(
    parser_output: dict[str, object],
) -> list[Replacement]:
    """
    Extracts file.replacement_1, file.replacement_2, and so on.

    Each replacement has this shape:

        {
            "line_num_ref": 126,
            "find": "old text",
            "replace_with": "new text",
        }
    """
    file_value = parser_output.get("file")

    if not isinstance(file_value, dict):
        raise FindReplaceError(
            "file is required in parser_output and must be an object"
        )

    file_obj = cast(dict[str, object], file_value)
    replacements_by_index: dict[int, Replacement] = {}

    for key, value in file_obj.items():
        match = re.fullmatch(r"replacement_(\d+)", key)

        if not match:
            continue

        index = int(match.group(1))

        if index < 1:
            raise FindReplaceError(
                f"{key} must start at replacement_1"
            )

        if not isinstance(value, dict):
            raise FindReplaceError(
                f"{key} must be an object"
            )

        if index in replacements_by_index:
            raise FindReplaceError(
                f"duplicate replacement index: {index}"
            )

        replacement_obj = cast(dict[str, object], value)

        find_value = replacement_obj.get("find")
        if not isinstance(find_value, str) or not find_value:
            raise FindReplaceError(
                f"{key}.find must be a non-empty string"
            )

        replace_with_value = replacement_obj.get("replace_with")
        if not isinstance(replace_with_value, str):
            raise FindReplaceError(
                f"{key}.replace_with must be a string"
            )

        line_num_ref = _parse_line_num_ref(
            replacement_obj.get("line_num_ref"),
            index - 1,
        )

        replacements_by_index[index] = {
            "line_num_ref": line_num_ref,
            "find": find_value,
            "replace_with": replace_with_value,
        }

    if not replacements_by_index:
        raise FindReplaceError(
            "replacements missing (expected at least file.replacement_1)"
        )

    indexes = sorted(replacements_by_index)
    expected_indexes = list(range(1, len(indexes) + 1))

    if indexes != expected_indexes:
        raise FindReplaceError(
            "replacement keys must be consecutive, starting at replacement_1"
        )

    return [
        replacements_by_index[index]
        for index in indexes
    ]


def _parse_line_num_ref(
    value: object,
    replacement_index: int,
) -> int | None:
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()

        if not value.isdigit():
            raise FindReplaceError(
                f"replacements[{replacement_index}].line_num_ref must be a positive integer if provided"
            )

        value = int(value)

    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise FindReplaceError(
            f"replacements[{replacement_index}].line_num_ref must be a positive integer if provided"
        )

    return value


def _line_number_at_offset(text: str, offset: int) -> int:
    """
    Returns a 1-based line number for a character offset.
    """
    return text.count("\n", 0, offset) + 1



def _find_match_offset(
    text: str,
    find_text: str,
    line_num_ref: int | None,
    replacement_index: int,
) -> tuple[int, int]:
    """
    Finds one exact occurrence of find_text.

    If multiple occurrences exist, line_num_ref is required and selects
    the occurrence whose starting line is closest to the referenced line.
    Equal-distance ties fail deterministically.
    """
    matches = [
        match.start()
        for match in re.finditer(re.escape(find_text), text)
    ]

    if not matches:
        raise FindReplaceError(
            f"replacements[{replacement_index}] find text was not found"
        )

    if len(matches) == 1:
        start_offset = matches[0]
        return start_offset, len(matches)

    if line_num_ref is None:
        raise FindReplaceError(
            f"replacements[{replacement_index}] find text is ambiguous ({len(matches)} matches); provide line_num_ref"
        )

    distances = [
        abs(
            _line_number_at_offset(text, match_offset)
            - line_num_ref
        )
        for match_offset in matches
    ]

    closest_distance = min(distances)

    closest_matches = [
        match_offset
        for match_offset, distance in zip(matches, distances)
        if distance == closest_distance
    ]

    if len(closest_matches) != 1:
        raise FindReplaceError(
            f"replacements[{replacement_index}] find text remains ambiguous near line_num_ref={line_num_ref}"
        )

    return closest_matches[0], len(matches)


class Replacement(TypedDict):
    line_num_ref: int | str | None
    find: str
    replace_with: str


class ReplacementOperation(TypedDict):
    index: int
    start_offset: int
    end_offset: int
    find: str
    replace_with: str
    line_num_ref: int | None
    total_match_count: int


class ReplacementAudit(TypedDict):
    index: int
    start_line: int
    end_line: int
    line_num_ref: int | None
    match_count_before_disambiguation: int
    find_characters: int
    replace_with_characters: int


def _apply_replacements(
    text: str,
    replacements: Iterable[Replacement],
) -> tuple[str, list[ReplacementAudit]]:
    """
    Applies exact text replacements against the original text.

    All match offsets are calculated before any replacement is applied.
    Replacements are then applied from bottom to top so earlier offsets
    remain valid.
    """
    operations: list[ReplacementOperation] = []

    for replacement_index, replacement in enumerate(replacements):
        find_text = replacement["find"]
        replace_with = replacement["replace_with"]

        line_num_ref = _parse_line_num_ref(
            replacement["line_num_ref"],
            replacement_index,
        )

        if not find_text:
            raise FindReplaceError(
                f"replacements[{replacement_index}].find must be a non-empty string"
            )

        start_offset, total_match_count = _find_match_offset(
            text=text,
            find_text=find_text,
            line_num_ref=line_num_ref,
            replacement_index=replacement_index,
        )

        end_offset = start_offset + len(find_text)

        operations.append(
            {
                "index": replacement_index,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "find": find_text,
                "replace_with": replace_with,
                "line_num_ref": line_num_ref,
                "total_match_count": total_match_count,
            }
        )

    operations.sort(key=lambda operation: operation["start_offset"])

    for index in range(len(operations) - 1):
        previous = operations[index]
        current = operations[index + 1]

        if current["start_offset"] < previous["end_offset"]:
            raise FindReplaceError(
                "replacement regions overlap: replacement_{previous['index'] + 1} and replacement_{current['index'] + 1}"
            )

    updated_text = text

    for operation in reversed(operations):
        start_offset = operation["start_offset"]
        end_offset = operation["end_offset"]

        updated_text = (
            updated_text[:start_offset]
            + operation["replace_with"]
            + updated_text[end_offset:]
        )

    audit: list[ReplacementAudit] = []

    for operation in operations:
        start_offset = operation["start_offset"]
        end_offset = operation["end_offset"]

        audit.append(
            {
                "index": operation["index"],
                "start_line": _line_number_at_offset(
                    text,
                    start_offset,
                ),
                "end_line": _line_number_at_offset(
                    text,
                    max(start_offset, end_offset - 1),
                ),
                "line_num_ref": operation["line_num_ref"],
                "match_count_before_disambiguation": operation[
                    "total_match_count"
                ],
                "find_characters": len(operation["find"]),
                "replace_with_characters": len(
                    operation["replace_with"]
                ),
            }
        )

    return updated_text, audit


def _make_unified_diff(
    original_path: Path,
    original_text: str,
    updated_text: str,
    n: int,
) -> str:
    original_text = (
        original_text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    updated_text = (
        updated_text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    original_lines = original_text.splitlines(keepends=True)
    updated_lines = updated_text.splitlines(keepends=True)

    fromfile = f"a/{original_path.name}"
    tofile = f"b/{original_path.name}"

    diff_lines = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=fromfile,
        tofile=tofile,
        n=n,
        lineterm=DIFF_NEW_LINE_TERMINATOR,
    )

    return "".join(diff_lines)


def _hint_for_message(message: str) -> str:
    if "find text was not found" in message:
        return (
            "Hint: Make replacement.find match the original text exactly, "
            "including whitespace and line endings."
        )

    if "find text is ambiguous" in message:
        return (
            "Hint: Add line_num_ref or make replacement.find more specific."
        )

    if "remains ambiguous" in message:
        return (
            "Hint: Use a more specific find value or a line_num_ref closer "
            "to only one occurrence."
        )

    if "replacement regions overlap" in message:
        return (
            "Hint: Ensure replacement regions do not overlap in the original "
            "file."
        )

    if "replacements missing" in message:
        return (
            "Hint: Provide file.replacement_1 with find and replace_with."
        )

    if "must be a non-negative integer" in message:
        return (
            "Hint: Set params.unified_diff_n_context_lines_around "
            "to an integer >= 0."
        )

    if "original target file does not exist" in message:
        return (
            "Hint: Verify output_dir and file.file_name point to an "
            "existing file."
        )

    if "output_dir must be a non-empty string" in message:
        return (
            "Hint: Ensure parser_output.output_dir is a non-empty string."
        )

    if "file.file_name must be a non-empty string" in message:
        return (
            "Hint: Ensure file.file_name is a non-empty string."
        )

    if "must be a string" in message:
        return (
            "Hint: Check that find and replace_with are strings."
        )

    return (
        "Hint: Check the replacement fields and ensure each find value "
        "matches exactly one region, or provide line_num_ref."
    )


def _build_error_with_context(
    *,
    error: Exception,
    parser_output: object,
    stage: str,
) -> str:
    output_dir = ""
    file_name = ""

    if isinstance(parser_output, dict):
        parsed_output = cast(dict[str, object], parser_output)
        output_dir_value = parsed_output.get("output_dir", "")

        if isinstance(output_dir_value, str):
            output_dir = output_dir_value

        parsed_output = cast(dict[str, object], parser_output)

        file_value = parsed_output.get("file")

        if isinstance(file_value, dict):
            file_obj = cast(dict[str, object], file_value)
            file_name_value = file_obj.get("file_name", "")

            if isinstance(file_name_value, str):
                file_name = file_name_value

    message = str(error)
    context = (
        f"Context: stage={stage}; "
        f"output_dir={output_dir!r}; "
        f"file_name={file_name!r}"
    )
    hint = _hint_for_message(message)

    return f"{message}\n{context}\n{hint}"


def _find_and_replace_step(
    params: dict[str, object],
    inputs: dict[str, object],
    state: dict[str, object],
    dt: float,  # pyright: ignore[reportUnusedParameter]
) -> tuple[dict[str, object], dict[str, object]]:
    parser_output = inputs.get("parser_output")
    typed_parser_output: dict[str, object] | None = None
    stage = "init"

    try:
        if not isinstance(parser_output, dict):
            raise FindReplaceError(
                "missing or invalid parser_output (expected an object)"
            )

        typed_parser_output = cast(dict[str, object], parser_output)

        stage = "extract_output_dir"
        output_dir = _extract_output_dir(typed_parser_output)

        stage = "extract_target_file_and_content"
        original_path, original_text = _extract_target_file_and_content(
            typed_parser_output,
            output_dir,
        )

        original_text = (
            original_text
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        stage = "extract_replacements"
        replacements = _extract_replacements(typed_parser_output)

        stage = "validate_diff_params"
        n = params.get(
            "unified_diff_n_context_lines_around",
            UNIFIED_DIFF_N_CONTEXT_LINES_AROUND,
        )

        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise FindReplaceError(
                "params.unified_diff_n_context_lines_around must be a non-negative integer"
            )

        stage = "apply_replacements"
        updated_text, audit = _apply_replacements(
            original_text,
            replacements,
        )

        stage = "make_patch"
        patch = _make_unified_diff(
            original_path=original_path,
            original_text=original_text,
            updated_text=updated_text,
            n=n,
        )

        file_result = {
            "ok": True,
            "file_name": original_path.name,
            "output_format": original_path.suffix.lstrip("."),
            "patch": patch,
            "error": None,
            "file_preview": (
                updated_text[:500]
                + ("..." if len(updated_text) > 500 else "")
            ),
            "audit": audit,
        }

        return (
            {
                "data": {
                    "output_dir": output_dir,
                    "file": file_result,
                },
                "error": None,
            },
            state,
        )

    except (
        FindReplaceError,
        OSError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
    ) as error:
        error_message = _build_error_with_context(
            error=error,
            parser_output=typed_parser_output,
            stage=stage,
        )

        output_dir = ""

        if typed_parser_output is not None:
            output_dir_value = typed_parser_output.get("output_dir", "")

            if isinstance(output_dir_value, str):
                output_dir = output_dir_value

        return (
            {
                "data": {
                    "output_dir": output_dir,
                    "file": {
                        "ok": False,
                        "file_name": "",
                        "output_format": "",
                        "patch": "",
                        "error": error_message,
                        "file_preview": "",
                        "audit": [],
                    },
                },
                "error": error_message,
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
                "Generates a unified-diff patch by replacing exact text "
                "regions in a file. Input must be parser_output with "
                "action='edit_file', output_dir, and file.file_name "
                "(or file.content), plus replacement_1 and optionally "
                "replacement_2, replacement_3, and so on. Each replacement "
                "uses find, replace_with, and an optional line_num_ref for "
                "disambiguating repeated matches. Replacements are applied "
                "against the original file, and overlapping regions fail."
            ),
        )
    )

__all__ = ["NEW_FILE_INPUT_PORTS", "NEW_FILE_OUTPUT_PORTS", "register_find_and_replace_unit"]
