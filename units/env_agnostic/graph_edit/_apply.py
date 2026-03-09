"""Shared: get current graph from inputs, apply edit via graph_edits, return outputs and state."""
from __future__ import annotations

from typing import Any


def apply_edit(
    inputs: dict[str, Any],
    state: dict[str, Any],
    edit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from assistants.graph_edits import apply_graph_edit

    current = inputs.get("graph")
    if current is None:
        current = {}
    updated = apply_graph_edit(current, edit)
    return ({"graph": updated}, state)
