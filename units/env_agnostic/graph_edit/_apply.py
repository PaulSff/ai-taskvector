"""Shared: get current graph from inputs, apply edit via graph_edits, return outputs and state."""
from __future__ import annotations

from typing import Any


def get_graph_from_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Get current graph from inputs: either inputs['graph'] or inputs['data']['graph'] (from inject)."""
    g = inputs.get("graph")
    if g is not None and isinstance(g, dict):
        return g
    data = inputs.get("data")
    if isinstance(data, dict):
        g = data.get("graph")
        if g is not None and isinstance(g, dict):
            return g
    return {}


def apply_edit(
    inputs: dict[str, Any],
    state: dict[str, Any],
    edit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from core.graph.graph_edits import apply_graph_edit

    current = get_graph_from_inputs(inputs)
    updated = apply_graph_edit(current, edit)
    return ({"graph": updated}, state)
