# run: pytest -q units/coding/edit_file/test_edit_file_unit.py
from __future__ import annotations

import atexit
import shutil
from pathlib import Path

from units.coding.edit_file.edit_file import _edit_file_step

# Keep these in sync with the unit module defaults/expectations.
DEFAULT_FILENAME = "new_file"
DEFAULT_OUTPUT_FORMAT = "txt"

# Hardcoded work directory next to this test file; cleaned up on exit.
_WORK_DIR = Path(__file__).resolve().parent / ".pytest_edit_file_work"


def _cleanup() -> None:
    shutil.rmtree(_WORK_DIR, ignore_errors=True)


atexit.register(_cleanup)
_WORK_DIR.mkdir(parents=True, exist_ok=True)


def _make_parser_output(*, output_dir: Path, file_payload: dict) -> dict:
    return {
        "output_dir": str(output_dir),
        "file": file_payload,
    }


def _reset_target_file(*, output_dir: Path, name: str, content: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    p = output_dir / name
    p.write_text(content, encoding="utf-8")
    return p


def test_edit_file_step_happy_path_applies_patch_and_writes_file():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir, name="new_file.txt", content="hello\nworld\n"
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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is True
    assert data["error"] is None
    assert data["output_path"] == str(target_path)
    assert "file_preview" in data and isinstance(data["file_preview"], str)

    assert target_path.read_text(encoding="utf-8") == "hello\nWORLD\n"


def test_edit_file_step_supports_wrapper_action_edit_file():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(
        output_dir=output_dir, name="new_file.txt", content="hello\nworld\n"
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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "hello\nWORLD\n"


def test_edit_file_step_missing_payload_returns_error():
    parser_output = {
        "output_dir": str(_WORK_DIR),
        # "file" missing
    }

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is False
    assert out["error"] == data["error"]
    assert "missing or invalid file payload" in data["error"]


def test_edit_file_step_payload_file_not_dict_returns_error():
    parser_output = {
        "output_dir": str(_WORK_DIR),
        "file": "not-a-dict",
    }

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is False
    assert "missing or invalid file payload" in data["error"]


def test_edit_file_step_missing_output_dir_returns_error():
    parser_output = {
        # output_dir missing
        "file": {
            "file_name": "new_file.txt",
            "patch": "",
        }
    }

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is False
    # Current behavior errors earlier as "missing or invalid file payload"
    # because output_dir missing makes _extract_file_payload_and_output_dir return (None, None).
    assert "missing or invalid file payload" in data["error"]


def test_edit_file_step_output_dir_wrong_type_returns_error():
    parser_output = {
        "output_dir": object(),
        "file": {
            "file_name": "new_file.txt",
            "patch": "not needed",
        },
    }

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is False
    # With current code, output_dir parsing fails and results in a bogus Path string,
    # which then fails at "target file does not exist".
    assert "target file does not exist" in data["error"]


def test_edit_file_step_patch_missing_or_empty_returns_error():
    parser_output = {
        "output_dir": str(_WORK_DIR),
        "file": {
            "file_name": "new_file.txt",
            "patch": "   ",  # empty/whitespace
        },
    }

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is False
    assert "file payload must contain 'patch' as a non-empty string" in data["error"]


def test_edit_file_step_target_missing_returns_error():
    # Ensure file does not exist
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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is False
    assert "target file does not exist" in data["error"]


def test_edit_file_step_context_mismatch_returns_formatted_error():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(output_dir=output_dir, name="new_file.txt", content="hello\nworld\n")

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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is False
    assert "context mismatch while applying patch" in data["error"]
    assert "expected_context_line" in data["error"]
    assert "actual_context_line" in data["error"]
    assert target_path.read_text(encoding="utf-8") == "hello\nworld\n"


def test_edit_file_step_patch_target_basename_mismatch_returns_error():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(output_dir=output_dir, name="new_file.txt", content="hello\nworld\n")

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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is False
    assert "patch target filename does not match the target file" in data["error"]
    assert target_path.read_text(encoding="utf-8") == "hello\nworld\n"



def test_edit_file_step_writes_preview_truncation():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(output_dir=output_dir, name="new_file.txt", content=("a\n" * 300))

    parser_output = _make_parser_output(
        output_dir=output_dir,
        file_payload={
            "file_name": "new_file.txt",
            "patch": """\
--- a/new_file.txt
+++ b/new_file.txt
@@ -1 +1 @@
-a
+bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
""",
        },
    )

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is True

    assert target_path.read_text(encoding="utf-8").startswith("a\n")
    assert "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in target_path.read_text(encoding="utf-8")

    preview = data["file_preview"]
    assert isinstance(preview, str)
    assert preview.endswith("...")



def test_edit_file_step_standard_unified_diff_single_hunk_multiple_context_lines():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(output_dir=output_dir, name="new_file.txt", content="line1\nline2\nline3\nline4\n")

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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "line1\nLINE2\nline3\nline4\n"


def test_edit_file_step_standard_unified_diff_multiple_hunks():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(output_dir=output_dir, name="new_file.txt", content="a\nb\nc\nd\ne\n")

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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "a\nB\nc\nd\nE\n"


def test_edit_file_step_standard_unified_diff_context_alignment():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(output_dir=output_dir, name="new_file.txt", content="p\nq\nr\ns\n")

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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "p\nq\nR\ns\n"


def test_edit_file_step_handles_crlf_in_target():
    output_dir = _WORK_DIR
    target_path = _reset_target_file(output_dir=output_dir, name="new_file.txt", content="hello\r\nworld\r\n")

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

    out, _state = _edit_file_step(
        params={},
        inputs={"parser_output": parser_output},
        state={},
        dt=0.0,
    )

    data = out["data"]
    assert data["ok"] is True
    assert target_path.read_text(encoding="utf-8") == "hello\nWORLD\n"
