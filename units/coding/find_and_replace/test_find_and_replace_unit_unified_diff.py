# Run:
# pytest -q units/coding/find_and_replace/test_find_and_replace_unit_unified_diff.py

from pathlib import Path
from typing import TypedDict, cast

from unidiff.patch import PatchSet

from units.coding.find_and_replace.find_and_replace import (
    _find_and_replace_step,  # pyright: ignore[reportPrivateUsage]
)

UNIFIED_DIFF_N_CONTEXT_LINES_AROUND = 3

class AuditEntry(TypedDict):
    start_line: int
    line_num_ref: int
    match_count_before_disambiguation: int


class FileResult(TypedDict):
    ok: bool
    file_name: str
    output_format: str
    patch: str
    error: str | None
    file_preview: str
    audit: list[AuditEntry]


class StepData(TypedDict):
    output_dir: str
    file: FileResult


class StepResult(TypedDict):
    data: StepData
    error: str | None


def _run_unit(
    tmp_path: Path,
    replacement: dict[str, object],
    file_text: str = "START\nold\nEND\n",
) -> tuple[StepResult, dict[str, object]]:
    test_file = tmp_path / "test_file.py"

    _ = test_file.write_text(file_text, encoding="utf-8")

    raw_result = _find_and_replace_step(
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
    )

    raw_out, state = raw_result

    # The production function returns a broad dict type, but the test knows
    # the expected result shape.
    out = cast(StepResult, cast(object, raw_out))

    return out, state

def test_find_and_replace_unit_generates_valid_unified_diff(
    tmp_path: Path,
) -> None:
    """Exact text is replaced and the resulting unified diff is parseable."""
    raw_out, _state = _run_unit(
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

    out = cast(StepResult, cast(object, raw_out))
    file_result = out["data"]["file"]

    assert file_result["ok"] is True

    patch_text = file_result["patch"]
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



def test_find_and_replace_unit_errors_when_replacement_1_missing(
    tmp_path: Path,
) -> None:
    """The unit fails when no replacement_N object is provided."""
    out, _state = _run_unit(
        tmp_path,
        {},
    )

    file_result = out["data"]["file"]

    assert file_result["ok"] is False
    assert file_result["patch"] == ""

    error = file_result["error"]
    assert isinstance(error, str)
    assert "replacements missing" in error


def test_find_and_replace_unit_errors_when_find_text_not_found(
    tmp_path: Path,
) -> None:
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

    file_result = out["data"]["file"]

    assert file_result["ok"] is False
    assert file_result["patch"] == ""

    error = file_result["error"]
    assert isinstance(error, str)
    assert "find text was not found" in error



def test_find_and_replace_unit_errors_when_find_text_is_ambiguous(
    tmp_path: Path,
) -> None:
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

    file_result = out["data"]["file"]

    assert file_result["ok"] is False
    assert file_result["patch"] == ""

    error = file_result["error"]
    assert isinstance(error, str)
    assert "find text is ambiguous" in error


def test_find_and_replace_unit_uses_line_num_ref_to_disambiguate(
    tmp_path: Path,
) -> None:
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

    file_result = out["data"]["file"]

    assert file_result["ok"] is True

    updated_text = file_result["file_preview"]
    assert updated_text.startswith(
        "before\nold\nmiddle\nnew\nafter\n"
    )

    audit = file_result["audit"]
    assert len(audit) == 1

    audit_entry = audit[0]
    assert audit_entry["start_line"] == 4
    assert audit_entry["line_num_ref"] == 4
    assert audit_entry["match_count_before_disambiguation"] == 2


def test_find_and_replace_unit_errors_when_line_num_ref_is_invalid(
    tmp_path: Path,
) -> None:
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

    file_result = out["data"]["file"]

    assert file_result["ok"] is False

    error = file_result["error"]
    assert isinstance(error, str)
    assert "line_num_ref" in error

def test_find_and_replace_unit_errors_when_line_num_ref_tie_remains(
    tmp_path: Path,
) -> None:
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
        file_text="old\nmiddle\nold\n",
    )

    file_result = out["data"]["file"]

    assert file_result["ok"] is False

    error = file_result["error"]
    assert isinstance(error, str)
    assert "remains ambiguous" in error


def test_find_and_replace_unit_insert_empty_string(
    tmp_path: Path,
) -> None:
    """replace_with='' deletes the matched text."""
    out, _state = _run_unit(
        tmp_path,
        {
            "replacement_1": {
                "find": "old1\nold2\n",
                "replace_with": "",
            }
        },
        file_text="A\nold1\nold2\nB\n",
    )

    file_result = out["data"]["file"]

    assert file_result["ok"] is True

    patch = PatchSet(file_result["patch"])
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
    tmp_path: Path,
) -> None:
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

    file_result = out["data"]["file"]

    assert file_result["ok"] is True

    patch_text = file_result["patch"]
    assert patch_text.strip()

    _ = PatchSet(patch_text)

def test_find_and_replace_unit_errors_when_replacement_regions_overlap(
    tmp_path: Path,
) -> None:
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
        file_text="old\nmiddle\nend\n",
    )

    file_result = out["data"]["file"]

    assert file_result["ok"] is False
    assert file_result["patch"] == ""

    error = file_result["error"]
    assert isinstance(error, str)
    assert "replacement regions overlap" in error

def test_find_and_replace_unit_supports_multiple_replacements(
    tmp_path: Path,
) -> None:
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
        file_text="first_old\nkeep\nsecond_old\n",
    )

    file_result = out["data"]["file"]

    assert file_result["ok"] is True

    patch = PatchSet(file_result["patch"])
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

def test_find_and_replace_unit_find_is_exact_text(
    tmp_path: Path,
) -> None:
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

    file_result = out["data"]["file"]

    assert file_result["ok"] is False

    error = file_result["error"]
    assert isinstance(error, str)
    assert "find text was not found" in error
