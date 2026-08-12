from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from unidiff.patch import PatchSet

from units.registry import UnitSpec, register_unit

NEW_FILE_INPUT_PORTS = [("parser_output", "Any")]
NEW_FILE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

DEFAULT_FILENAME = "new_file"
DEFAULT_OUTPUT_FORMAT = "txt"


def _sanitize_extension(ext: str) -> str:
    ext = (ext or "").strip().lower()
    if not ext:
        return DEFAULT_OUTPUT_FORMAT
    ext = ext.removeprefix(".")
    ext = ext.replace("/", "").replace("\\", "")
    return ext or DEFAULT_OUTPUT_FORMAT


def _extract_file_payload_and_output_dir(
    parser_output: Any,
) -> tuple[dict[str, Any] | None, Path | None]:
    if isinstance(parser_output, list):
        parser_output = {}
    if not isinstance(parser_output, dict):
        return None, None

    raw_output_dir = parser_output.get("output_dir")
    if raw_output_dir is None:
        return None, None

    try:
        output_dir = Path(str(raw_output_dir).strip()).expanduser().resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None, None

    payload = parser_output.get("file")
    if not isinstance(payload, dict):
        return None, None

    return payload, output_dir


def _normalize_input_wrapper(parser_output: Any) -> Any:
    # Supports:
    # { "action": "edit_file", "output_dir": "...", "file": {...} }
    if isinstance(parser_output, dict) and parser_output.get("action") == "edit_file":
        return {
            "output_dir": parser_output.get("output_dir"),
            "file": parser_output.get("file"),
        }
    return parser_output


@dataclass
class _ApplyMismatch:
    hunk_index: int
    old_start: int
    new_start: int
    expected: str
    actual: str
    original_index: int


class PatchApplyError(ValueError):
    def __init__(self, *, message: str, mismatch: _ApplyMismatch | None = None) -> None:
        super().__init__(message)
        self.mismatch = mismatch


def _extract_patch_target_basename(patched_file: Any) -> str:
    # unidiff: patched_file.source_file and patched_file.target_file are FileHeader objects/strings
    # We treat them as paths like "a/foo.txt" or "b/foo.txt".
    # Prefer target_file if present; otherwise source_file.
    for attr in ("target_file", "source_file"):
        v = getattr(patched_file, attr, None)
        if v:
            s = str(v)
            # drop common prefixes like "a/" or "b/"
            if "/" in s:
                s = s.split("/")[-1]
            return s
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

    current = orig_lines

    for hunk_index, hunk in enumerate(patched_file):
        idx = hunk.source_start - 1  # convert 1-based to 0-based

        if idx < 0 or idx > len(current):
            raise PatchApplyError(
                message="patch application failed: context mismatch while applying patch "
                f"(hunk starts out of range: idx={idx})"
            )

        new_chunk: list[str] = []
        cursor = idx

        for line in hunk:
            # unidiff Line objects:
            # - line.line_type in {' ', '+', '-'}
            # - line.value is the line content WITHOUT the leading diff marker, newline preserved if present in input
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
                    raise PatchApplyError(message="patch application failed: deletion mismatch while applying patch")

                cursor += 1

            elif line.line_type == "+":
                added = line.value
                added_no_nl = added.removesuffix("\n")
                new_chunk.append(added_no_nl)


            else:
                raise PatchApplyError(
                    message=f"patch application failed: unknown diff line type: {line.line_type!r}"
                )

        # Replace [idx:cursor] with new_chunk
        current = current[:idx] + new_chunk + current[cursor:]

    return "\n".join(current)


def _format_context_error(e: PatchApplyError) -> str:
    m = getattr(e, "mismatch", None)
    if m is None:
        return str(e)

    lines: list[str] = []
    lines.append("patch application failed: context mismatch while applying patch")
    lines.append(f"hunk_index: {m.hunk_index}")
    lines.append(f"old_start: {m.old_start}")
    lines.append(f"new_start: {m.new_start}")
    lines.append(f"line_index_in_original: {m.original_index}")
    lines.append(f"expected_context_line: {m.expected!r}")
    lines.append(f"actual_context_line: {m.actual!r}")
    lines.append("")
    lines.append("hint: adjust the patch context lines to match the target file (the current file differs from the expected context).")
    return "\n".join(lines)


def _edit_file_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out: dict[str, Any] = {"ok": False, "output_path": "", "error": None, "file_preview": ""}

    parser_output = inputs.get("parser_output")
    parser_output = _normalize_input_wrapper(parser_output)

    payload, output_dir = _extract_file_payload_and_output_dir(parser_output)

    if not payload:
        out["error"] = "missing or invalid file payload (expected parser_output['file'])"
        return ({"data": out, "error": out["error"]}, state)

    if not isinstance(output_dir, Path):
        out["error"] = "output_dir is required in parser_output"
        return ({"data": out, "error": out["error"]}, state)

    patch = payload.get("patch")
    if not isinstance(patch, str) or not patch.strip():
        out["error"] = "file payload must contain 'patch' as a non-empty string"
        return ({"data": out, "error": out["error"]}, state)

    output_format = _sanitize_extension(payload.get("output_format") or DEFAULT_OUTPUT_FORMAT)

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
        out["error"] = f"target file does not exist: {target_path}"
        return ({"data": out, "error": out["error"]}, state)

    try:
        original = target_path.read_text(encoding="utf-8")
    except OSError as e:
        out["error"] = f"cannot read target file: {e}"
        return ({"data": out, "error": out["error"]}, state)

    expected_target_basename = target_path.name

    try:
        updated = _apply_unified_diff_with_unidiff(
            original,
            patch,
            expected_target_basename=expected_target_basename,
        )
    except PatchApplyError as e:
        out["error"] = _format_context_error(e)
        return ({"data": out, "error": out["error"]}, state)
    except ValueError as e:
        out["error"] = f"patch application failed: {e}"
        return ({"data": out, "error": out["error"]}, state)
    except (TypeError, UnicodeDecodeError) as e:
        out["error"] = f"patch application failed: {e}"
        return ({"data": out, "error": out["error"]}, state)

    try:
        target_path.write_text(updated, encoding="utf-8")
    except OSError as e:
        out["error"] = f"cannot write updated file: {e}"
        return ({"data": out, "error": out["error"]}, state)

    out["ok"] = True
    out["output_path"] = str(target_path)
    out["file_preview"] = updated[:500] + ("..." if len(updated) > 500 else "")
    return ({"data": out, "error": None}, state)


def register_edit_file_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="EditFile",
            input_ports=NEW_FILE_INPUT_PORTS,
            output_ports=NEW_FILE_OUTPUT_PORTS,
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


__all__ = ["NEW_FILE_INPUT_PORTS", "NEW_FILE_OUTPUT_PORTS", "register_edit_file_unit"]
