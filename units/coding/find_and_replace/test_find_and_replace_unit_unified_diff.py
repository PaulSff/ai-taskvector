# Run: pytest -q units/coding/find_and_replace/test_find_and_replace_unit_unified_diff.py
from pathlib import Path

from unidiff.patch import PatchSet

# Adjust this import to your actual module path
from units.coding.find_and_replace.find_and_replace import _find_and_replace_step

UNIFIED_DIFF_N_CONTEXT_LINES_AROUND = 3 # must be > 0 , so we have at lease 1 line to search around the patch

def test_find_and_replace_unit_generates_valid_unified_diff(tmp_path):
    """Validates that the FindAndReplace unit generates a syntactically
    correct unified diff that unidiff can parse, and that the hunk contains
    the expected removed and added lines between the specified anchor markers."""

    # Arrange: create a temp target file
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "line1\n"
        "START_ANCHOR\n"
        "old_middle_a\n"
        "old_middle_b\n"
        "END_ANCHOR\n"
        "line_after\n",
        encoding="utf-8",
    )

    output_dir = str(tmp_path)

    inputs = {
        "parser_output": {
            "action": "edit_file",
            "output_dir": output_dir,
            "file": {
                "file_name": "test_file.py",
                "replacement_1": {
                    "find_starting_anchor_line": "START_ANCHOR",
                    "find_ending_anchor_line": "END_ANCHOR",
                    "insert_in_between": "new_middle_1\nnew_middle_2\n",
                },
            },
        }
    }

    params = {"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND}
    state = {}
    dt = 0.0

    # Act
    out, _new_state = _find_and_replace_step(params=params, inputs=inputs, state=state, dt=dt)

    # Assert: unit returned ok + a parseable unified diff
    assert out["data"]["file"]["ok"] is True
    patch_text = out["data"]["file"]["patch"]
    assert isinstance(patch_text, str) and patch_text.strip()

    patch = PatchSet(patch_text)

    # Basic sanity: one file patched, one hunk
    assert len(patch) == 1
    patched_file = patch[0]
    assert Path(patched_file.path).name == "test_file.py"
    assert len(patched_file) == 1

    hunk = patched_file[0]

    changed_texts = []
    for line in hunk:
        if getattr(line, "is_added", False) or getattr(line, "is_removed", False):
            changed_texts.append(line.value)

    removed = [line.value for line in hunk if getattr(line, "is_removed", False)]
    added = [line.value for line in hunk if getattr(line, "is_added", False)]

    expected_removed_added = {
        "removed": ["old_middle_a\n", "old_middle_b\n"],
        "added": ["new_middle_1\n", "new_middle_2\n"],
    }
    assert removed == expected_removed_added["removed"]
    assert added == expected_removed_added["added"]
    assert changed_texts == expected_removed_added["removed"] + expected_removed_added["added"]

    context = [line.value for line in hunk if getattr(line, "is_context", False)]
    assert "START_ANCHOR\n" in context
    assert "END_ANCHOR\n" in context


def test_find_and_replace_unit_errors_when_replacement_1_missing(tmp_path):
    """If no replacement_N keys exist under parser_output['file'], the unit must fail."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "START_ANCHOR\nold\nEND_ANCHOR\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    # intentionally no "replacement_1"
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is False
    assert out["data"]["file"]["patch"] == ""
    assert "replacements missing" in out["data"]["file"]["error"]


def test_find_and_replace_unit_errors_when_starting_anchor_not_found(tmp_path):
    """If find_starting_anchor_line has 0 matches, the unit must fail."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "somewhere_else\nEND_ANCHOR\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    "replacement_1": {
                        "find_starting_anchor_line": "START_ANCHOR",
                        "find_ending_anchor_line": "END_ANCHOR",
                        "insert_in_between": "X\n",
                    },
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is False
    assert "starting anchor not found" in out["data"]["file"]["error"]


def test_find_and_replace_unit_errors_when_ending_anchor_not_found(tmp_path):
    """If find_ending_anchor_line has 0 matches, the unit must fail."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "START_ANCHOR\nold\nmissing_end\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    "replacement_1": {
                        "find_starting_anchor_line": "START_ANCHOR",
                        "find_ending_anchor_line": "END_ANCHOR",
                        "insert_in_between": "X\n",
                    },
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is False
    assert "ending anchor not found" in out["data"]["file"]["error"]


def test_find_and_replace_unit_errors_when_starting_anchor_ambiguous(tmp_path):
    """If find_starting_anchor_line matches multiple lines, the unit must fail."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "START_ANCHOR\nx\nSTART_ANCHOR\nEND_ANCHOR\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    "replacement_1": {
                        "find_starting_anchor_line": "START_ANCHOR",
                        "find_ending_anchor_line": "END_ANCHOR",
                        "insert_in_between": "X\n",
                    },
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is False
    assert "starting anchor ambiguous" in out["data"]["file"]["error"]


def test_find_and_replace_unit_errors_when_ending_anchor_ambiguous(tmp_path):
    """If find_ending_anchor_line matches multiple lines, the unit must fail."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "START_ANCHOR\nx\nEND_ANCHOR\nEND_ANCHOR\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    "replacement_1": {
                        "find_starting_anchor_line": "START_ANCHOR",
                        "find_ending_anchor_line": "END_ANCHOR",
                        "insert_in_between": "X\n",
                    },
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is False
    assert "ending anchor ambiguous" in out["data"]["file"]["error"]


def test_find_and_replace_unit_errors_when_ending_before_or_at_start(tmp_path):
    """If ending anchor occurs before/at starting anchor, the unit must fail."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "END_ANCHOR\nSTART_ANCHOR\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    "replacement_1": {
                        "find_starting_anchor_line": "START_ANCHOR",
                        "find_ending_anchor_line": "END_ANCHOR",
                        "insert_in_between": "X\n",
                    },
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is False
    assert "ending anchor occurs before/at starting anchor" in out["data"]["file"]["error"]


def test_find_and_replace_unit_insert_empty_string(tmp_path):
    """insert_in_between='' should delete the lines between anchors."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "A\nSTART_ANCHOR\nold1\nold2\nEND_ANCHOR\nB\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    "replacement_1": {
                        "find_starting_anchor_line": "START_ANCHOR",
                        "find_ending_anchor_line": "END_ANCHOR",
                        "insert_in_between": "",
                    },
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is True
    patch = PatchSet(out["data"]["file"]["patch"])

    assert len(patch) == 1
    hunk = patch[0][0]

    removed = [line.value for line in hunk if getattr(line, "is_removed", False)]
    added = [line.value for line in hunk if getattr(line, "is_added", False)]

    assert removed == ["old1\n", "old2\n"]
    assert added == []


def test_find_and_replace_unit_insert_without_trailing_newline(tmp_path):
    """Even if insert_in_between lacks a trailing newline, we still require a parseable diff."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "START_ANCHOR\nold\nEND_ANCHOR\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    "replacement_1": {
                        "find_starting_anchor_line": "START_ANCHOR",
                        "find_ending_anchor_line": "END_ANCHOR",
                        "insert_in_between": "new_without_trailing_newline",
                    },
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is True
    patch_text = out["data"]["file"]["patch"]
    assert isinstance(patch_text, str) and patch_text.strip()
    PatchSet(patch_text)  # must not raise


def test_find_and_replace_unit_anchor_matching_is_substring(tmp_path):
    """Anchors use substring matching (anchor in line), not exact line equality."""
    test_file = tmp_path / "test_file.py"
    test_file.write_text(
        "prefix START_ANCHOR suffix\nold\nsuffix END_ANCHOR suffix\n",
        encoding="utf-8",
    )

    out, _state = _find_and_replace_step(
        params={"unified_diff_n_context_lines_around": UNIFIED_DIFF_N_CONTEXT_LINES_AROUND},
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    "replacement_1": {
                        "find_starting_anchor_line": "START_ANCHOR",
                        "find_ending_anchor_line": "END_ANCHOR",
                        "insert_in_between": "X\n",
                    },
                },
            }
        },
        state={},
        dt=0.0,
    )

    assert out["data"]["file"]["ok"] is True
    PatchSet(out["data"]["file"]["patch"])  # diff should still be syntactically valid
