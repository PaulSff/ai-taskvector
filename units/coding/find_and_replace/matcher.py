from __future__ import annotations

import re

from units.coding.find_and_replace.schemas import FindReplaceError


def line_number_at_offset(text: str, offset: int) -> int:
    """
    Returns a 1-based line number for a character offset.
    """
    return text.count("\n", 0, offset) + 1


def find_match_offset(
    text: str,
    find_text: str,
    line_num_ref: int | None,
    replacement_index: int,
) -> tuple[int, int]:
    """
    Finds one exact occurrence of find_text.

    If multiple occurrences exist, line_num_ref is required and selects
    the occurrence whose starting line is closest to the referenced line.
    Equal-distance ties fail deterministically.
    """
    matches = [
        match.start()
        for match in re.finditer(re.escape(find_text), text)
    ]

    if not matches:
        raise FindReplaceError(
            f"replacements[{replacement_index}] find text was not found"
        )

    if len(matches) == 1:
        start_offset = matches[0]
        return start_offset, len(matches)

    if line_num_ref is None:
        raise FindReplaceError(
            f"replacements[{replacement_index}] find text is ambiguous "
            f"({len(matches)} matches); provide line_num_ref"
        )

    distances = [
        abs(
            line_number_at_offset(text, match_offset)
            - line_num_ref
        )
        for match_offset in matches
    ]

    closest_distance = min(distances)

    closest_matches = [
        match_offset
        for match_offset, distance in zip(matches, distances)
        if distance == closest_distance
    ]

    if len(closest_matches) != 1:
        raise FindReplaceError(
            f"replacements[{replacement_index}] find text remains ambiguous "
            f"near line_num_ref={line_num_ref}"
        )

    start_offset = closest_matches[0]
    return start_offset, len(matches)
