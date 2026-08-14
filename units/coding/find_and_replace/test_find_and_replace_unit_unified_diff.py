# Run:
# pytest -q units/coding/find_and_replace/test_find_and_replace_unit_unified_diff.py

from pathlib import Path

from unidiff.patch import PatchSet

from units.coding.find_and_replace.find_and_replace import (
    _find_and_replace_step,
)

UNIFIED_DIFF_N_CONTEXT_LINES_AROUND = 3


def _run_unit(tmp_path, replacement, file_text="START\nold\nEND\n"):
    test_file = tmp_path / "test_file.py"
    test_file.write_text(file_text, encoding="utf-8")

    return _find_and_replace_step(
        params={
            "unified_diff_n_context_lines_around": (
                UNIFIED_DIFF_N_CONTEXT_LINES_AROUND
            )
        },
        inputs={
            "parser_output": {
                "action": "edit_file",
                "output_dir": str(tmp_path),
                "file": {
                    "file_name": "test_file.py",
                    **replacement,
                },
            }
        },
        state={},
        dt=0.0,
    )


def test_find_and_replace_unit_generates_valid_unified_diff(tmp_path):
    """Exact text is replaced and the resulting unified diff is parseable."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "old_middle_a\nold_middle_b\n",
                "replace_with": "new_middle_1\nnew_middle_2\n",
            }
        },
        file_text=(
            "line1\n"
            "START_ANCHOR\n"
            "old_middle_a\n"
            "old_middle_b\n"
            "END_ANCHOR\n"
            "line_after\n"
        ),
    )

    assert out["data"]["file"]["ok"] is True

    patch_text = out["data"]["file"]["patch"]
    assert isinstance(patch_text, str)
    assert patch_text.strip()

    patch = PatchSet(patch_text)

    assert len(patch) == 1

    patched_file = patch[0]
    assert Path(patched_file.path).name == "test_file.py"
    assert len(patched_file) == 1

    hunk = patched_file[0]

    removed = [
        line.value
        for line in hunk
        if getattr(line, "is_removed", False)
    ]
    added = [
        line.value
        for line in hunk
        if getattr(line, "is_added", False)
    ]

    assert removed == [
        "old_middle_a\n",
        "old_middle_b\n",
    ]
    assert added == [
        "new_middle_1\n",
        "new_middle_2\n",
    ]

    changed_texts = [
        line.value
        for line in hunk
        if (
            getattr(line, "is_added", False)
            or getattr(line, "is_removed", False)
        )
    ]

    assert changed_texts == removed + added

    context = [
        line.value
        for line in hunk
        if getattr(line, "is_context", False)
    ]

    assert "START_ANCHOR\n" in context
    assert "END_ANCHOR\n" in context


def test_find_and_replace_unit_errors_when_replacement_1_missing(tmp_path):
    """The unit fails when no replacement_N object is provided."""
    out, _state = _run_unit(
        tmp_path,
        {},
    )

    assert out["data"]["file"]["ok"] is False
    assert out["data"]["file"]["patch"] == ""
    assert "replacements missing" in out["data"]["file"]["error"]


def test_find_and_replace_unit_errors_when_find_text_not_found(tmp_path):
    """The unit fails when find does not occur in the original file."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "does_not_exist\n",
                "replace_with": "new\n",
            }
        },
    )

    assert out["data"]["file"]["ok"] is False
    assert out["data"]["file"]["patch"] == ""
    assert "find text was not found" in out["data"]["file"]["error"]


def test_find_and_replace_unit_errors_when_find_text_is_ambiguous(tmp_path):
    """Repeated find text requires line_num_ref."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "old\n",
                "replace_with": "new\n",
            }
        },
        file_text=(
            "before\n"
            "old\n"
            "middle\n"
            "old\n"
            "after\n"
        ),
    )

    assert out["data"]["file"]["ok"] is False
    assert out["data"]["file"]["patch"] == ""
    assert "find text is ambiguous" in out["data"]["file"]["error"]


def test_find_and_replace_unit_uses_line_num_ref_to_disambiguate(
    tmp_path,
):
    """line_num_ref selects the matching occurrence nearest the reference."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "line_num_ref": 4,
                "find": "old\n",
                "replace_with": "new\n",
            }
        },
        file_text=(
            "before\n"
            "old\n"
            "middle\n"
            "old\n"
            "after\n"
        ),
    )

    assert out["data"]["file"]["ok"] is True

    updated_text = out["data"]["file"]["file_preview"]
    assert updated_text.startswith(
        "before\n"
        "old\n"
        "middle\n"
        "new\n"
        "after\n"
    )

    audit = out["data"]["file"]["audit"]
    assert len(audit) == 1
    assert audit[0]["start_line"] == 4
    assert audit[0]["line_num_ref"] == 4
    assert audit[0]["match_count_before_disambiguation"] == 2


def test_find_and_replace_unit_errors_when_line_num_ref_is_invalid(
    tmp_path,
):
    """line_num_ref must be a positive integer when provided."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "line_num_ref": 0,
                "find": "old\n",
                "replace_with": "new\n",
            }
        },
    )

    assert out["data"]["file"]["ok"] is False
    assert "line_num_ref" in out["data"]["file"]["error"]


def test_find_and_replace_unit_errors_when_line_num_ref_tie_remains(
    tmp_path,
):
    """An equally close line_num_ref must not select arbitrarily."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "line_num_ref": 2,
                "find": "old\n",
                "replace_with": "new\n",
            }
        },
        file_text=(
            "old\n"
            "middle\n"
            "old\n"
        ),
    )

    assert out["data"]["file"]["ok"] is False
    assert "remains ambiguous" in out["data"]["file"]["error"]


def test_find_and_replace_unit_insert_empty_string(tmp_path):
    """replace_with='' deletes the matched text."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "old1\nold2\n",
                "replace_with": "",
            }
        },
        file_text=(
            "A\n"
            "old1\n"
            "old2\n"
            "B\n"
        ),
    )

    assert out["data"]["file"]["ok"] is True

    patch = PatchSet(out["data"]["file"]["patch"])
    assert len(patch) == 1

    hunk = patch[0][0]

    removed = [
        line.value
        for line in hunk
        if getattr(line, "is_removed", False)
    ]
    added = [
        line.value
        for line in hunk
        if getattr(line, "is_added", False)
    ]

    assert removed == ["old1\n", "old2\n"]
    assert added == []


def test_find_and_replace_unit_insert_without_trailing_newline(
    tmp_path,
):
    """A replacement without a trailing newline still produces a parseable diff."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "old\n",
                "replace_with": "new_without_trailing_newline",
            }
        },
    )

    assert out["data"]["file"]["ok"] is True

    patch_text = out["data"]["file"]["patch"]
    assert isinstance(patch_text, str)
    assert patch_text.strip()

    PatchSet(patch_text)


def test_find_and_replace_unit_errors_when_replacement_regions_overlap(
    tmp_path,
):
    """Overlapping exact-text replacements must fail."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "old\nmiddle\n",
                "replace_with": "first\n",
            },
            "replacement_2": {
                "find": "middle\n",
                "replace_with": "second\n",
            },
        },
        file_text=(
            "old\n"
            "middle\n"
            "end\n"
        ),
    )

    assert out["data"]["file"]["ok"] is False
    assert out["data"]["file"]["patch"] == ""
    assert "replacement regions overlap" in out["data"]["file"]["error"]


def test_find_and_replace_unit_supports_multiple_replacements(
    tmp_path,
):
    """Multiple non-overlapping replacements are applied successfully."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "first_old\n",
                "replace_with": "first_new\n",
            },
            "replacement_2": {
                "find": "second_old\n",
                "replace_with": "second_new\n",
            },
        },
        file_text=(
            "first_old\n"
            "keep\n"
            "second_old\n"
        ),
    )

    assert out["data"]["file"]["ok"] is True

    patch = PatchSet(out["data"]["file"]["patch"])
    assert len(patch) == 1

    hunk = patch[0][0]

    removed = [
        line.value
        for line in hunk
        if getattr(line, "is_removed", False)
    ]
    added = [
        line.value
        for line in hunk
        if getattr(line, "is_added", False)
    ]

    assert removed == [
        "first_old\n",
        "second_old\n",
    ]
    assert added == [
        "first_new\n",
        "second_new\n",
    ]


def test_find_and_replace_unit_find_is_exact_text(tmp_path):
    """Near-matching text must not be treated as a match."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "old_value = 1\n",
                "replace_with": "old_value = 2\n",
            }
        },
        file_text="old_value = 10\n",
    )

    assert out["data"]["file"]["ok"] is False
    assert "find text was not found" in out["data"]["file"]["error"]
