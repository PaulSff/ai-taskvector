from __future__ import annotations

import datetime
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypedDict, cast

from unidiff.patch import PatchSet

from units.registry import UnitSpec, register_unit

EDIT_FILE_INPUT_PORTS = [("parser_output", "Any")]
EDIT_FILE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

DEFAULT_FILENAME = "new_file"
DEFAULT_OUTPUT_FORMAT = "txt"
DEFAULT_FUZZY_CONTEXT_WINDOW = 6


@dataclass
class EditFileOutput:
    ok: bool = False
    output_path: str = ""
    error: str | None = None
    uncommited_changes: str = ""
    md5_before: str = ""
    md5_after: str = ""
    timestamp_utc: str = ""


@dataclass
class _ApplyMismatch:
    hunk_index: int
    old_start: int
    new_start: int
    expected: str
    actual: str
    original_index: int


def _sanitize_extension(ext: str) -> str:
    ext = (ext or "").strip().lower()
    if not ext:
        return DEFAULT_OUTPUT_FORMAT
    ext = ext.removeprefix(".")
    ext = ext.replace("/", "").replace("\\", "")
    return ext or DEFAULT_OUTPUT_FORMAT


def _extract_file_payload_and_output_dir(
    parser_output: object,
) -> tuple[dict[str, object] | None, Path | None]:
    if isinstance(parser_output, list):
        parser_output = {}

    if not isinstance(parser_output, dict):
        return None, None

    typed_parser_output = cast(
        dict[str, object],
        cast(object, parser_output),
    )

    raw_output_dir = typed_parser_output.get("output_dir")
    if raw_output_dir is None:
        return None, None

    try:
        output_dir = Path(str(raw_output_dir).strip()).expanduser().resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None, None

    payload = typed_parser_output.get("file")
    if not isinstance(payload, dict):
        return None, None

    typed_payload = cast(
        dict[str, object],
        cast(object, payload),
    )

    return typed_payload, output_dir


class NormalizedEditFile(TypedDict):
    output_dir: object
    file: object


def _normalize_input_wrapper(parser_output: object) -> object:
    """
    Supports:

    {
        "action": "edit_file",
        "output_dir": "...",
        "file": {...},
    }
    """
    if not isinstance(parser_output, dict):
        return parser_output

    typed_parser_output = cast(dict[str, object], parser_output)

    if typed_parser_output.get("action") == "edit_file":
        normalized: NormalizedEditFile = {
            "output_dir": typed_parser_output.get("output_dir"),
            "file": typed_parser_output.get("file"),
        }
        return normalized

    return cast(
        dict[str, object],
        {
            "output_dir": typed_parser_output.get("output_dir"),
            "file": typed_parser_output.get("file"),
        },
    )


class PatchApplyError(ValueError):
    mismatch: _ApplyMismatch | None

    def __init__(
        self,
        *,
        message: str,
        mismatch: _ApplyMismatch | None = None,
    ) -> None:
        super().__init__(message)
        self.mismatch = mismatch


def _extract_patch_target_basename(patched_file: object) -> str:
    # unidiff: patched_file.source_file and patched_file.target_file
    # are FileHeader objects/strings.
    for attr in ("target_file", "source_file"):
        value = cast(object, getattr(patched_file, attr, None))

        if value:
            path = str(value)
            return path.rsplit("/", 1)[-1]

    return ""


def _apply_unified_diff_with_unidiff(
    original: str,
    patch: str,
    *,
    expected_target_basename: str,
) -> str:
    original = original.replace("\r\n", "\n").replace("\r", "\n")
    orig_lines = original.split("\n")

    try:
        patchset = PatchSet(patch.splitlines(True))  # keepends semantics
    except Exception as e:
        raise PatchApplyError(message=f"patch application failed: unable to parse unified diff: {e}") from e

    if len(patchset) != 1:
        raise PatchApplyError(
            message=(
                "patch application failed: expected a unified diff containing exactly one file "
                f"but found {len(patchset)}"
            )
        )

    patched_file = patchset[0]
    patch_basename = _extract_patch_target_basename(patched_file)

    if not patch_basename:
        raise PatchApplyError(
            message=(
                "patch application failed: unable to determine the patched filename from the unified diff "
                "(missing ---/+++ header filenames)"
            )
        )

    if patch_basename != expected_target_basename:
        raise PatchApplyError(
            message=(
                "patch application failed: patch target filename does not match the target file "
                f"(patch: {patch_basename!r}, target: {expected_target_basename!r})"
            )
        )

    # main loop
    current = orig_lines

    for hunk_index, hunk in enumerate(patched_file):
        expected_idx = hunk.source_start - 1  # convert 1-based to 0-based

        if expected_idx < 0 or expected_idx > len(current):
            raise PatchApplyError(
                message="patch application failed: context mismatch while applying patch (hunk starts out of range: idx={expected_idx})"
            )

        # First try strict application at expected_idx.
        try:
            new_chunk: list[str] = []
            cursor = expected_idx

            for line in hunk:
                if line.line_type == " ":
                    expected = line.value
                    expected_no_nl = expected.removesuffix("\n")
                    actual = current[cursor] if cursor < len(current) else "<EOF>"

                    if actual != expected_no_nl:
                        mismatch = _ApplyMismatch(
                            hunk_index=hunk_index,
                            old_start=hunk.source_start,
                            new_start=hunk.target_start,
                            expected=expected_no_nl,
                            actual=actual,
                            original_index=cursor,
                        )
                        raise PatchApplyError(
                            message="patch application failed: context mismatch while applying patch",
                            mismatch=mismatch,
                        )

                    new_chunk.append(actual)
                    cursor += 1

                elif line.line_type == "-":
                    expected = line.value
                    expected_no_nl = expected.removesuffix("\n")
                    actual = current[cursor] if cursor < len(current) else "<EOF>"

                    if actual != expected_no_nl:
                        raise PatchApplyError(
                            message="patch application failed: deletion mismatch while applying patch"
                        )

                    cursor += 1

                elif line.line_type == "+":
                    added = line.value
                    added_no_nl = added.removesuffix("\n")
                    new_chunk.append(added_no_nl)

                else:
                    raise PatchApplyError(
                        message=f"patch application failed: unknown diff line type: {line.line_type!r}"
                    )

            # Replace [expected_idx:cursor] with new_chunk
            current = current[:expected_idx] + new_chunk + current[cursor:]
            continue

        except PatchApplyError as e:
            # Fuzzy retry: only for context mismatch (not for deletion mismatch / parse / etc.)
            if getattr(e, "mismatch", None) is None:
                raise

            # Build contiguous context sequence from the hunk (lines with ' ')
            context_values: list[str] = [
                line.value.removesuffix("\n")
                for line in hunk
                if line.line_type == " "
            ]
            if len(context_values) < 3:
                # Not enough context to fuzzy-match
                raise

            # Find how many source lines occur before the first context line in the hunk
            # (only ' ' and '-' consume source; '+' does not)
            lines_before_first_context = 0
            for line in hunk:
                if line.line_type == " ":
                    break
                if line.line_type in {"-", " "}:
                    lines_before_first_context += 1
                elif line.line_type == "+":
                    pass

            first_context_line_value = context_values[0]

            window = DEFAULT_FUZZY_CONTEXT_WINDOW
            start_search = max(0, expected_idx - window)
            end_search = min(len(current), expected_idx + window)

            fuzzy_idx = expected_idx
            found = False

            for j in range(start_search, end_search):
                if current[j] != first_context_line_value:
                    continue

                # check full contiguous context match
                k = 0
                while k < len(context_values):
                    cj = j + k
                    if cj >= len(current) or current[cj] != context_values[k]:
                        break
                    k += 1

                if k == len(context_values):
                    candidate = j - lines_before_first_context
                    if 0 <= candidate <= len(current):
                        fuzzy_idx = candidate
                        found = True
                        break

            if not found or fuzzy_idx == expected_idx:
                raise

            # Apply again at fuzzy_idx (same logic as strict path)
            new_chunk = []
            cursor = fuzzy_idx

            for line in hunk:
                if line.line_type == " ":
                    expected = line.value.removesuffix("\n")
                    actual = current[cursor] if cursor < len(current) else "<EOF>"

                    if actual != expected:
                        mismatch = _ApplyMismatch(
                            hunk_index=hunk_index,
                            old_start=hunk.source_start,
                            new_start=hunk.target_start,
                            expected=expected,
                            actual=actual,
                            original_index=cursor,
                        )
                        raise PatchApplyError(
                            message="patch application failed: context mismatch while applying patch",
                            mismatch=mismatch,
                        )

                    new_chunk.append(actual)
                    cursor += 1

                elif line.line_type == "-":
                    expected = line.value.removesuffix("\n")
                    actual = current[cursor] if cursor < len(current) else "<EOF>"

                    if actual != expected:
                        raise PatchApplyError(
                            message="patch application failed: deletion mismatch while applying patch"
                        )

                    cursor += 1

                elif line.line_type == "+":
                    added_no_nl = line.value.removesuffix("\n")
                    new_chunk.append(added_no_nl)

                else:
                    raise PatchApplyError(
                        message=f"patch application failed: unknown diff line type: {line.line_type!r}"
                    )

            current = current[:fuzzy_idx] + new_chunk + current[cursor:]

    return "\n".join(current)



def _format_context_error(e: PatchApplyError) -> str:
    m = e.mismatch
    if m is None:
        return str(e)

    lines: list[str] = [
        "patch application failed: context mismatch while applying patch",
        f"hunk_index: {m.hunk_index}",
        f"old_start: {m.old_start}",
        f"new_start: {m.new_start}",
        f"line_index_in_original: {m.original_index}",
        f"expected_context_line: {m.expected!r}",
        f"actual_context_line: {m.actual!r}",
        "",
        (
            "hint: adjust the patch context lines to match the target file "
            "(the current file differs from the expected context)."
        ),
    ]
    return "\n".join(lines)


def _edit_file_step(
    params: dict[str, object],  # pyright: ignore[reportUnusedParameter]
    inputs: dict[str, object],
    state: dict[str, object],
    dt: float,  # pyright: ignore[reportUnusedParameter]
) -> tuple[dict[str, object], dict[str, object]]:
    # Define the output shape:
    out_obj = EditFileOutput()

    parser_output = inputs.get("parser_output")
    parser_output = _normalize_input_wrapper(parser_output)

    payload, output_dir = _extract_file_payload_and_output_dir(parser_output)

    if not payload:
        out_obj.error = "missing or invalid file payload (expected parser_output['file'])"
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)

    if not isinstance(output_dir, Path):
        out_obj.error = "output_dir is required in parser_output"
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)

    patch = payload.get("patch")
    if not isinstance(patch, str) or not patch.strip():
        out_obj.error = "file payload must contain 'patch' as a non-empty string"
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)

    raw_output_format = payload.get("output_format")
    output_format = _sanitize_extension(
        raw_output_format if isinstance(raw_output_format, str)
        else DEFAULT_OUTPUT_FORMAT
    )

    file_name = payload.get("file_name")
    if isinstance(file_name, str):
        file_name = file_name.strip()
    else:
        file_name = ""

    default_filename = f"{DEFAULT_FILENAME}.{output_format}"

    if file_name:
        chosen_filename = Path(file_name).name
        if not Path(chosen_filename).suffix:
            chosen_filename = f"{chosen_filename}.{output_format}"
    else:
        chosen_filename = default_filename

    target_path = output_dir / chosen_filename

    if not target_path.exists() or not target_path.is_file():
        out_obj.error = f"target file does not exist: {target_path}"
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)

    try:
        # read the original file
        original = target_path.read_text(encoding="utf-8")
        # compute MD5 of the original file
        md5_before = hashlib.md5(original.encode("utf-8")).hexdigest()
    except OSError as e:
        out_obj.error = f"cannot read target file: {e}"
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)

    expected_target_basename = target_path.name

    try:
        updated = _apply_unified_diff_with_unidiff(
            original,
            patch,
            expected_target_basename=expected_target_basename,
        )
    except PatchApplyError as e:
        out_obj.error = _format_context_error(e)
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)
    except ValueError as e:
        out_obj.error = f"patch application failed: {e}"
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)
    except (TypeError, UnicodeDecodeError) as e:
        out_obj.error = f"patch application failed: {e}"
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)

    try:
        # write the file modified on disk
        _ = target_path.write_text(updated, encoding="utf-8")
        # compute MD5 on the file modified
        md5_after = hashlib.md5(updated.encode("utf-8")).hexdigest()
    except OSError as e:
        out_obj.error = f"cannot write updated file: {e}"
        return ({"data": asdict(out_obj), "error": out_obj.error}, state)

    # Collect the output items:
    out_obj.ok = True
    out_obj.output_path = str(target_path)
    out_obj.uncommited_changes = patch
    out_obj.md5_before = md5_before
    out_obj.md5_after = md5_after
    out_obj.timestamp_utc = datetime.datetime.now(datetime.UTC).isoformat()

    return ({"data": asdict(out_obj), "error": None}, state)


def register_edit_file_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="EditFile",
            input_ports=EDIT_FILE_INPUT_PORTS,
            output_ports=EDIT_FILE_OUTPUT_PORTS,
            step_fn=_edit_file_step,
            environment_tags=["coding"],
            environment_tags_are_agnostic=False,
            description=(
                "Edit an existing text file by applying a unified-diff patch string in "
                "parser_output['file']['patch']. Reads parser_output['output_dir'] and "
                "parser_output['file']['file_name'] (or default). Overwrites the file in place. "
                "Uses python-unidiff to parse and apply hunks with context validation. "
                "Rejects patches that contain multiple files or whose ---/+++ filename does not match the target."
            ),
        )
    )


__all__ = ["EDIT_FILE_INPUT_PORTS", "EDIT_FILE_OUTPUT_PORTS", "register_edit_file_unit"]
