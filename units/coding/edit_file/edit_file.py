"""
EditFile unit description:
- Input is provided via a single port named `parser_output`.
- Expects `parser_output["output_dir"]` (directory containing the target file).
- Expects `parser_output["file"]` as a dict with:
  - `file_name` (optional): which file to edit; directory parts are ignored.
  - `output_format` (optional): extension hint (defaults to "txt") used only if `file_name` has no suffix.
  - `patch` (required): a unified-diff patch string (hunks like `@@ -old,+new @@` plus context lines).
- The unit reads the target file as UTF-8, applies the unified-diff patch, then overwrites the file in place.
- Output:
  - `data["ok"]`: boolean
  - `data["output_path"]`: edited file path (string)
  - `data["file_preview"]`: first 500 chars of updated content (string)
  - `data["error"]`: error message on failure

  Example (edit a file using unified diff)
  Inputs to `EditFile` (port value for `parser_output`):
  {
    "output_dir": "/Users/jm/ai-taskvector/mydata",
    "file": {
      "output_format": "py",
      "file_name": "hello_world.py",
      "patch": "@@ -1,5 +1,5 @@\\n-def main():\\n+def main():\\n"
    }
  }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def _extract_file_payload_and_output_dir(parser_output: Any) -> tuple[dict[str, Any] | None, Path | None]:
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


class _Hunk:
    def __init__(self, old_start: int, old_count: int, new_start: int, new_count: int, lines: list[str]) -> None:
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines = lines


def _parse_unified_diff(patch: str) -> list[_Hunk]:
    """
    Minimal unified-diff parser:
    - ignores file headers (---/+++)
    - reads @@ -a,b +c,d @@ hunks
    - collects hunk lines beginning with ' ', '+', '-'
    """
    patch = patch.replace("\r\n", "\n").replace("\r", "\n")
    lines = patch.split("\n")

    hunks: list[_Hunk] = []
    i = 0

    def parse_range(spec: str) -> tuple[int, int]:
        rest = spec[1:]  # strip leading '-' or '+'
        if "," in rest:
            start_s, count_s = rest.split(",", 1)
            return int(start_s), int(count_s)
        return int(rest), 1

    while i < len(lines):
        line = lines[i]
        if line.startswith("@@"):
            parts = line.split("@@")
            body = parts[1].strip() if len(parts) >= 2 else line.strip()
            tokens = body.split()
            if len(tokens) < 2:
                i += 1
                continue

            old_start, old_count = parse_range(tokens[0])
            new_start, new_count = parse_range(tokens[1])

            i += 1
            hunk_lines: list[str] = []
            while i < len(lines):
                if lines[i].startswith("@@"):
                    break
                if lines[i].startswith(("---", "+++", "diff ", "index ")):
                    break
                if lines[i] == "":
                    break
                prefix = lines[i][0]
                if prefix in (" ", "+", "-"):
                    hunk_lines.append(lines[i])
                    i += 1
                    continue
                break

            hunks.append(_Hunk(old_start, old_count, new_start, new_count, hunk_lines))
            continue

        i += 1

    return hunks


def _apply_unified_diff(original: str, patch: str) -> str:
    original = original.replace("\r\n", "\n").replace("\r", "\n")
    orig_lines = original.split("\n")

    hunks = _parse_unified_diff(patch)
    if not hunks:
        raise ValueError("patch contained no recognizable unified-diff hunks")

    out_lines: list[str] = []
    orig_cursor = 0

    for h in hunks:
        target_old_index = h.old_start - 1

        if target_old_index < orig_cursor:
            raise ValueError("patch hunks overlap or are out of order")

        out_lines.extend(orig_lines[orig_cursor:target_old_index])
        orig_cursor = target_old_index

        for hl in h.lines:
            if not hl:
                continue
            kind = hl[0]
            text = hl[1:]

            if kind == " ":
                if orig_cursor >= len(orig_lines) or orig_lines[orig_cursor] != text:
                    raise ValueError("context mismatch while applying patch")
                out_lines.append(text)
                orig_cursor += 1
            elif kind == "-":
                if orig_cursor >= len(orig_lines) or orig_lines[orig_cursor] != text:
                    raise ValueError("deletion mismatch while applying patch")
                orig_cursor += 1
            elif kind == "+":
                out_lines.append(text)

    out_lines.extend(orig_lines[orig_cursor:])
    return "\n".join(out_lines)


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

    try:
        updated = _apply_unified_diff(original, patch)
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
                "parser_output['file']['file_name'] (or default). Overwrites the file in place."
            ),
        )
    )


__all__ = ["NEW_FILE_INPUT_PORTS", "NEW_FILE_OUTPUT_PORTS", "register_edit_file_unit"]
