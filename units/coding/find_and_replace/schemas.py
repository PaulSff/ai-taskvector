
from __future__ import annotations

from typing import TypedDict


class FindReplaceError(ValueError):
    pass


class Replacement(TypedDict):
    line_num_ref: int | str | None
    find: str
    replace_with: str


class ReplacementOperation(TypedDict):
    index: int
    start_offset: int
    end_offset: int
    find: str
    replace_with: str
    line_num_ref: int | None
    total_match_count: int


class ReplacementAudit(TypedDict):
    index: int
    start_line: int
    end_line: int
    line_num_ref: int | None
    match_count_before_disambiguation: int
    find_characters: int
    replace_with_characters: int
