# run: pytest -q units/coding/edit_file/test_edit_file_unit.py
from __future__ import annotations

import atexit
import difflib
import shutil
from pathlib import Path
from typing import TypedDict, cast

from units.coding.edit_file.edit_file import (
    _edit_file_step,  # pyright: ignore[reportPrivateUsage]
)

# Keep these in sync with the unit module defaults/expectations.
DEFAULT_FILENAME = "new_file"
DEFAULT_OUTPUT_FORMAT = "txt"
DIFF_NEW_LINE_TERMINATOR = "\n"
UNIFIED_DIFF_N_CONTEXT_LINES_AROUND = 3 # must be > 0 , so we have at lease 1 line to search around the patch
# Hardcoded work directory next to this test file; cleaned up on exit.
_WORK_DIR = Path(__file__).resolve().parent / ".pytest_edit_file_work"


def _cleanup() -> None:
    shutil.rmtree(_WORK_DIR, ignore_errors=True)


_ = atexit.register(_cleanup)

_WORK_DIR.mkdir(parents=True, exist_ok=True)



class ParserOutput(TypedDict):
    output_dir: str
    file: dict[str, object]

class EditFileData(TypedDict):
    ok: bool
    error: str | None
    output_path: str
    file_preview: str


def _make_parser_output(
    *,
    output_dir: Path,
    file_payload: dict[str, object],
) -> ParserOutput:
    return {
        "output_dir": str(output_dir),
        "file": file_payload,
    }


def _reset_target_file(
    *,
    output_dir: Path,
    name: str,
    content: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / name
    _ = path.write_text(content, encoding="utf-8")

    return path


def test_edit_file_step_happy_path_applies_patch_and_writes_file():
    """Applies a valid unified diff patch and verifies the output
    file is written with updated contents and a preview is returned."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="hello\nworld\n",
    )

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "output_format": DEFAULT_OUTPUT_FORMAT,
            "patch": """\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1,2 +1,2 @@
 hello
-world
+WORLD
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])

    assert data["ok"] is True
    assert data["error"] is None
    assert data["output_path"] == str(target_path)
    assert isinstance(data["file_preview"], str)

    assert target_path.read_text(encoding="utf-8") == "hello\nWORLD\n"


def test_edit_file_step_supports_wrapper_action_edit_file():
    """Supports the wrapper parser_output format (action='edit_file')
    and verifies the patch is applied and the file is updated."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="hello\nworld\n",
    )

    parser_output = {
        "action": "edit_file",
        "output_dir": str(output_dir),
        "file": {
            "file_name": "new_file.txt",
            "patch": """\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1,2 +1,2 @@
 hello
-world
+WORLD
""",
        },
    }

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])

    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "hello\nWORLD\n"


def test_edit_file_step_missing_payload_returns_error():
    """Returns an error when parser_output is missing the required 'file' payload."""
    parser_output = {
        "output_dir": str(_WORK_DIR),
    }

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    error = data["error"]

    assert data["ok"] is False
    assert out["error"] == error
    assert error is not None
    assert "missing or invalid file payload" in error


def test_edit_file_step_payload_file_not_dict_returns_error():
    """Returns an error when parser_output['file'] exists but is not a dict."""
    parser_output = {
        "output_dir": str(_WORK_DIR),
        "file": "not-a-dict",
    }

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    error = data["error"]

    assert data["ok"] is False
    assert error is not None
    assert "missing or invalid file payload" in error


def test_edit_file_step_missing_output_dir_returns_error():
    """Returns an error when parser_output is missing 'output_dir'."""
    parser_output = {
        "file": {
            "file_name": "new_file.txt",
            "patch": "",
        },
    }

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    error = data["error"]

    assert data["ok"] is False
    assert error is not None
    # Current behavior errors earlier as "missing or invalid file payload"
    # because output_dir missing makes
    # _extract_file_payload_and_output_dir return (None, None).
    assert "missing or invalid file payload" in error


def test_edit_file_step_output_dir_wrong_type_returns_error():
    """Returns an error when parser_output['output_dir'] is
    the wrong type and the target file cannot be resolved."""
    parser_output = {
        "output_dir": object(),
        "file": {
            "file_name": "new_file.txt",
            "patch": "not needed",
        },
    }

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    error = data["error"]

    assert data["ok"] is False
    assert error is not None
    # With current code, output_dir parsing fails and results in a bogus
    # Path string, which then fails at "target file does not exist".
    assert "target file does not exist" in error


def test_edit_file_step_patch_missing_or_empty_returns_error():
    """Returns an error when the patch is missing or provided
    as an empty/whitespace-only string."""
    parser_output = {
        "output_dir": str(_WORK_DIR),
        "file": {
            "file_name": "new_file.txt",
            "patch": "   ",
        },
    }

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    error = data["error"]

    assert data["ok"] is False
    assert error is not None
    assert "file payload must contain 'patch' as a non-empty string" in error


def test_edit_file_step_target_missing_returns_error():
    """Returns an error when the target file referenced by the patch does not exist."""
    missing_path = _WORK_DIR / "does_not_exist.txt"
    if missing_path.exists():
        missing_path.unlink()

    parser_output = _make_parser_output(
        output_dir=_WORK_DIR,
        file_payload={
            "file_name": "does_not_exist.txt",
            "patch": """\
--- a/does_not_exist.txt
+++ b/does_not_exist.txt
@@ -1 +1 @@
-a
+b
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    error = data["error"]

    assert data["ok"] is False
    assert error is not None
    assert "target file does not exist" in error


def test_edit_file_step_context_mismatch_returns_formatted_error():
    """Returns a formatted patch mismatch error when applying a hunk fails
    due to mismatched removed context lines, and leaves the target file unchanged."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="hello\nworld\n",
    )

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": """\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1,2 +1,2 @@
 hello
-WORLD
+WORLD!!
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    error = data["error"]

    assert data["ok"] is False
    assert error is not None
    # With this implementation, this mismatch is triggered by the '-' deletion line.
    assert "deletion mismatch while applying patch" in error
    assert target_path.read_text(encoding="utf-8") == "hello\nworld\n"


def test_edit_file_step_patch_target_basename_mismatch_returns_error():
    """Returns an error when the patch's ---/+++ filename basename
    does not match the actual target file basename."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="hello\nworld\n",
    )

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": """\
--- a/other.txt
+++ b/other.txt
@@ -1,2 +1,2 @@
 hello
-world
+WORLD
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    error = data["error"]

    assert data["ok"] is False
    assert error is not None
    assert "patch target filename does not match the target file" in error
    assert target_path.read_text(encoding="utf-8") == "hello\nworld\n"


def test_edit_file_step_writes_preview_truncation():
    """Writes the updated file and returns a truncated
    file_preview string when the updated content exceeds
    the preview length limit."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="a\n" * 300,
    )

    long_b = (
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    )

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": f"""\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1 +1 @@
-a
+{long_b}
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])
    preview = data["file_preview"]

    assert data["ok"] is True

    updated = target_path.read_text(encoding="utf-8")
    # The patch replaces the first line (-a) with the long +bbbb... line.
    assert updated.splitlines()[0] == long_b
    assert long_b in updated

    assert isinstance(preview, str)
    assert preview.endswith("...")


def test_edit_file_step_standard_unified_diff_single_hunk_multiple_context_lines():
    """Applies a standard unified diff with one hunk and multiple context lines,
    verifying the correct single-line replacement."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="line1\nline2\nline3\nline4\n",
    )

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": """\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1,4 +1,4 @@
 line1
-line2
+LINE2
 line3
 line4
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])

    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == (
        "line1\nLINE2\nline3\nline4\n"
    )


def test_edit_file_step_standard_unified_diff_multiple_hunks():
    """Applies a standard unified diff containing multiple hunks
    and verifies all replacements are applied."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="a\nb\nc\nd\ne\n",
    )

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": """\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1,3 +1,3 @@
 a
-b
+B
 c
@@ -4,2 +4,2 @@
 d
-e
+E
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])

    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "a\nB\nc\nd\nE\n"


def test_edit_file_step_standard_unified_diff_context_alignment():
    """Applies a unified diff where context alignment matters,
    verifying the edit occurs at the correct line."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="p\nq\nr\ns\n",
    )

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": """\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1,4 +1,4 @@
 p
 q
-r
+R
 s
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])

    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "p\nq\nR\ns\n"


def test_edit_file_step_handles_crlf_in_target():
    """Applies a patch to a target file stored with CRLF
    and verifies output content is successfully updated."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="hello\r\nworld\r\n",
    )

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": """\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1,2 +1,2 @@
 hello
-world
+WORLD
""",
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])

    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "hello\nWORLD\n"


def test_edit_file_step_applies_unified_diff_generated_by_difflib():
    """Generates a unified diff using difflib and verifies
    _edit_file_step can apply it."""
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir,
        name="new_file.txt",
        content="hello\nworld\n",
    )

    original_lines = "hello\nworld\n".splitlines(keepends=True)
    updated_lines = "hello\nWORLD\n".splitlines(keepends=True)

    patch_lines = list(
        difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile="a/new_file.txt",
            tofile="b/new_file.txt",
            n=UNIFIED_DIFF_N_CONTEXT_LINES_AROUND,
            lineterm=DIFF_NEW_LINE_TERMINATOR,
        )
    )
    patch = "".join(patch_lines)

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": patch,
        },
    )

    out, _ = _edit_file_step(
        inputs={"parser_output": parser_output},
        state={},
    )

    data = cast(EditFileData, out["data"])

    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "hello\nWORLD\n"
