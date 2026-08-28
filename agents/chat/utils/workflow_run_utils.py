"""Shared helpers for agent chat workflow runs."""

from __future__ import annotations

import os
import sys

from core.schemas.primitives import is_string_keyed_dict


def collect_workflow_errors(
    outputs: object,
) -> list[tuple[str, str]]:
    """
    Collect non-null error port values from workflow outputs.

    Returns:
        A list of ``(unit_id, error_message)`` tuples for units that emitted
        an error.
    """
    errors: list[tuple[str, str]] = []

    if not is_string_keyed_dict(outputs):
        return errors

    for unit_id, unit_out in outputs.items():
        if not is_string_keyed_dict(unit_out):
            continue

        err = unit_out.get("error")

        if isinstance(err, str) and err.strip():
            errors.append((unit_id, err.strip()))

    return errors



def _workflow_debug_log_enabled() -> bool:
    return (os.environ.get("WORKFLOW_DEBUG_LOG") or "").strip() == "1"


def _workflow_debug_log(msg: str) -> None:
    if _workflow_debug_log_enabled():
        print(f"[workflow_debug] {msg}", file=sys.stderr, flush=True)
