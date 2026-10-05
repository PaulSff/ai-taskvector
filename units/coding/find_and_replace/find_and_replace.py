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
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

from core.schemas.primitives import Data, Output
from services.logging import setup_colored_logging
from units.coding.find_and_replace.matcher import (
    find_match_offset,
    line_number_at_offset,
)
from units.coding.find_and_replace.parsers import (
    as_object_dict,
    extract_output_dir,
    extract_replacements,
    extract_target_file_and_content,
    parse_line_num_ref,
)
from units.coding.find_and_replace.schemas import (
    FindReplaceError,
    Replacement,
    ReplacementAudit,
    ReplacementOperation,
)
from units.registry import UnitSpec, register_unit

NEW_FILE_INPUT_PORTS = [("parser_output", "Data")]
NEW_FILE_OUTPUT_PORTS = [("data", "Data"), ("error", "str")]

DIFF_NEW_LINE_TERMINATOR = "\n"
UNIFIED_DIFF_N_CONTEXT_LINES_AROUND = 3

logger = setup_colored_logging(logging.DEBUG)


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

        line_num_ref = parse_line_num_ref(
            replacement["line_num_ref"],
            replacement_index,
        )

        if not find_text:
            raise FindReplaceError(
                f"replacements[{replacement_index}].find must be a non-empty string"
            )

        start_offset, total_match_count = find_match_offset(
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
                "start_line": line_number_at_offset(
                    text,
                    start_offset,
                ),
                "end_line": line_number_at_offset(
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

    if isinstance(parser_output, Mapping):
        parsed_output = as_object_dict(parser_output, "parser_output must be a dict")

        output_dir_value = parsed_output.get("output_dir", "")
        if isinstance(output_dir_value, str):
            output_dir = output_dir_value

        file_value = parsed_output.get("file")
        if isinstance(file_value, Mapping):
            file_obj = as_object_dict(file_value, "file must be a dict")
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
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,  # pyright: ignore[reportUnusedParameter]
) -> Output:
    parser_output = inputs.get("parser_output")
    typed_parser_output: Data | None = None
    stage = "init"

    try:
        typed_parser_output = as_object_dict(
            parser_output,
            "missing or invalid parser_output (expected an object)",
        )

        stage = "extract_output_dir"
        output_dir = extract_output_dir(typed_parser_output)


        stage = "extract_target_file_and_content"
        original_path, original_text = extract_target_file_and_content(
            typed_parser_output,
            output_dir,
        )

        original_text = (
            original_text
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        stage = "extract_replacements"
        replacements = extract_replacements(typed_parser_output)

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

        logger.info(
            "Find-and-replace succeeded: file=%s replacements=%d changed=%s patch_characters=%d",
            original_path,
            len(audit),
            original_text != updated_text,
            len(patch),
        )

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
        file_name = ""

        if typed_parser_output is not None:
            output_dir_value = typed_parser_output.get("output_dir", "")

            if isinstance(output_dir_value, str):
                output_dir = output_dir_value

            file_value = typed_parser_output.get("file")

            if isinstance(file_value, dict):
                file_name_value = file_value.get("file_name")

                if isinstance(file_name_value, str):
                    file_name = file_name_value

        logger.warning(
            "Find-and-replace failed: stage=%s output_dir=%r "
            "file_name=%r error=%s",
            stage,
            output_dir,
            file_name,
            error_message,
        )

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
