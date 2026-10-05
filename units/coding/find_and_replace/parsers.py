from __future__ import annotations

import logging
import re
from pathlib import Path

from core.schemas.primitives import Data
from services.logging import setup_colored_logging
from units.coding.find_and_replace.schemas import FindReplaceError, Replacement

logger = setup_colored_logging(logging.DEBUG)


def as_object_dict(value: object, error: str) -> Data:
    if not isinstance(value, dict):
        raise FindReplaceError(error)
    return value


def extract_output_dir(parser_output: object) -> str:
    parsed = as_object_dict(parser_output, "parser_output must be an object")

    output_dir = parsed.get("output_dir")
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise FindReplaceError("output_dir must be a non-empty string")

    return output_dir.strip()


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def extract_target_file_and_content(
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
    parsed = as_object_dict(
        parser_output,
        "missing or invalid parser_output (expected object with action='edit_file')",
    )

    if parsed.get("action") != "edit_file":
        raise FindReplaceError(
            "missing or invalid parser_output (expected object with action='edit_file')"
        )

    file_obj = as_object_dict(
        parsed.get("file"),
        "file is required in parser_output and must be an object",
    )

    file_name = file_obj.get("file_name")
    if not isinstance(file_name, str) or not file_name.strip():
        raise FindReplaceError("file.file_name must be a non-empty string")

    file_name = file_name.strip()

    output_dir_path = Path(output_dir).expanduser().resolve()
    original_path = (output_dir_path / file_name).resolve()

    try:
        original_path.relative_to(output_dir_path)
    except ValueError as exc:
        raise FindReplaceError(f"file path escapes output_dir: {file_name}") from exc

    content = file_obj.get("content")
    if isinstance(content, str):
        original_text = normalize_text(content)
        source = "file.content"
    else:
        if not original_path.exists() or not original_path.is_file():
            raise FindReplaceError(f"original target file does not exist: {original_path}")

        original_text = normalize_text(original_path.read_text(encoding="utf-8"))
        source = "file on disk"

    logger.info(
        "Find-and-replace: extracted target file content path=%s, source=%s, length=%d",
        original_path,
        source,
        len(original_text),
    )

    return original_path, original_text


def extract_replacements(parser_output: Data) -> list[Replacement]:
    file_value = parser_output.get("file")
    file_obj = as_object_dict(
        file_value,
        "file is required in parser_output and must be an object",
    )

    replacements_by_index: dict[int, Replacement] = {}

    for key, value in file_obj.items():
        match = re.fullmatch(r"replacement_(\d+)", key)
        if not match:
            continue

        index = int(match.group(1))
        if index < 1:
            raise FindReplaceError(f"{key} must start at replacement_1")

        replacement_obj = as_object_dict(value, f"{key} must be an object")

        if index in replacements_by_index:
            raise FindReplaceError(f"duplicate replacement index: {index}")

        find_value = replacement_obj.get("find")
        if not isinstance(find_value, str) or not find_value:
            raise FindReplaceError(f"{key}.find must be a non-empty string")

        replace_with_value = replacement_obj.get("replace_with")
        if not isinstance(replace_with_value, str):
            raise FindReplaceError(f"{key}.replace_with must be a string")

        line_num_ref = parse_line_num_ref(
            replacement_obj.get("line_num_ref"),
            index - 1,
        )

        replacements_by_index[index] = {
            "line_num_ref": line_num_ref,
            "find": normalize_text(find_value),
            "replace_with": normalize_text(replace_with_value),
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

    return [replacements_by_index[index] for index in indexes]


def parse_line_num_ref(
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
