"""
NewFile: write arbitrary code/text files from parsed LLM output (no LLM call).

Usage:
- The ProcessAgent provides `parser_output` shaped like:
  - `parser_output["output_dir"]`:
    - `"output_dir": "./out"`
  - and `parser_output["file"]` with:
    - `output_format`: a file extension hint like "py", "js", "json", "xml", "txt", "sh", etc. (any string accepted)
    - `content`: the exact text to write (written as-is)
    - `file_name` (optional): desired filename (e.g., "main.py", "package.json"). If omitted, defaults to "new_file.<output_format>".

Example parser_output:

{
  "output_dir": "./out",
  "file": {
    "output_format": "py",
    "file_name": "hello_world.py",
    "content": "def main():\\n    print('hello world')\\n\\nif __name__ == '__main__':\\n    main()\\n"
  }
}

Expected result:
- writes `${output_dir}/hello_world.py` (or a unique suffixed name if it already exists).

Example for JSON output:

{
  "output_dir": "./out",
  "file": {
    "output_format": "json",
    "file_name": "config.json",
    "content": "{\\n  \\"mode\\": \\"dev\\"\\n}\\n"
  }
}
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from units.registry import UnitSpec, register_unit

NEW_FILE_INPUT_PORTS = [("parser_output", "Any")]
NEW_FILE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

DEFAULT_FILENAME = "new_file"
DEFAULT_OUTPUT_FORMAT = "txt"


def _sanitize_extension(ext: str) -> str:
    ext = (ext or "").strip().lower()
    if not ext:
        return DEFAULT_OUTPUT_FORMAT

    # allow values like ".py" or "py"
    ext = ext.removeprefix(".")
    ext = ext.replace("/", "").replace("\\", "")
    return ext or DEFAULT_OUTPUT_FORMAT


def _unique_path(output_dir: Path, desired_path: Path) -> Path:
    """
    If desired_path already exists inside output_dir, append suffixes:
    <stem>_1<suffix>, <stem>_2<suffix>, ...
    """
    if desired_path.parent != output_dir:
        desired_path = output_dir / desired_path.name

    candidate = desired_path
    i = 1
    while candidate.exists():
        candidate = output_dir / f"{desired_path.stem}_{i}{desired_path.suffix}"
        i += 1
    return candidate


def _extract_file_payload_and_output_dir(
    parser_output: object,
) -> tuple[dict[str, object] | None, Path | None]:
    """
    Expects parser_output shaped like:
    {
        "output_dir": "...",
        "file": {
            "output_format": "...",
            "content": "...",
            "file_name": "optional",
        },
    }
    """
    if isinstance(parser_output, list):
        parser_output = {}

    if not isinstance(parser_output, dict):
        return None, None

    parsed_output = cast(dict[str, object], parser_output)

    raw_output_dir = parsed_output.get("output_dir")
    if raw_output_dir is None:
        return None, None

    try:
        output_dir = Path(str(raw_output_dir).strip()).expanduser().resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None, None

    raw_payload = parsed_output.get("file")
    if not isinstance(raw_payload, dict):
        return None, None

    payload = cast(dict[str, object], raw_payload)
    return payload, output_dir


def _generic_file_step(
    params: dict[str, object],
    inputs: dict[str, object],
    state: dict[str, object],
    dt: float
) -> tuple[dict[str, object], dict[str, object]]:
    out: dict[str, object] = {
        "ok": False,
        "output_path": "",
        "error": None,
        "file_preview": "",
    }

    parser_output = inputs.get("parser_output")

    if isinstance(parser_output, dict):
        parsed_output = cast(dict[str, object], parser_output)

        # Support the optional wrapper shape:
        # {
        #     "action": "new_file",
        #     "output_dir": "...",
        #     "file": {...},
        # }
        if parsed_output.get("action") == "new_file":
            parser_output = {
                "output_dir": parsed_output.get("output_dir"),
                "file": parsed_output.get("file"),
            }

    payload, output_dir = _extract_file_payload_and_output_dir(
        cast(object, parser_output)
    )

    if not payload:
        out["error"] = (
            "missing or invalid file payload "
            "(expected parser_output['file'])"
        )
        return {"data": out, "error": out["error"]}, state

    if output_dir is None:
        out["error"] = "output_dir is required in parser_output"
        return {"data": out, "error": out["error"]}, state

    content = payload.get("content")
    if not isinstance(content, str):
        out["error"] = "file payload must contain 'content' as a string"
        return {"data": out, "error": out["error"]}, state

    raw_output_format = payload.get("output_format")
    if isinstance(raw_output_format, str) and raw_output_format:
        output_format = _sanitize_extension(raw_output_format)
    else:
        output_format = DEFAULT_OUTPUT_FORMAT

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        out["error"] = f"cannot create output_dir: {error}"
        return {"data": out, "error": out["error"]}, state

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

    desired_path = output_dir / chosen_filename
    file_path = _unique_path(output_dir, desired_path)

    try:
        _ = file_path.write_text(content, encoding="utf-8")
    except OSError as error:
        out["error"] = f"cannot write file: {error}"
        return {"data": out, "error": out["error"]}, state

    out["ok"] = True
    out["output_path"] = str(file_path)
    out["file_preview"] = content[:500] + (
        "..." if len(content) > 500 else ""
    )

    return {"data": out, "error": None}, state


def register_new_file_writer() -> None:
    register_unit(
        UnitSpec(
            type_name="NewFile",
            input_ports=NEW_FILE_INPUT_PORTS,
            output_ports=NEW_FILE_OUTPUT_PORTS,
            step_fn=_generic_file_step,
            environment_tags=["coding"],
            environment_tags_are_agnostic=False,
            description=(
                "Write an arbitrary code/text file from a file payload "
                "(content written as-is, output_format treated as extension hint, optional file_name). "
                "Uses parser_output['output_dir'] and parser_output['file'] only. "
                "No LLM; use with ProcessAgent."
            ),
        )
    )


__all__ = [
    "NEW_FILE_INPUT_PORTS",
    "NEW_FILE_OUTPUT_PORTS",
    "register_new_file_writer",
]
