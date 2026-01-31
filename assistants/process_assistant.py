"""
Process Assistant backend: apply graph edit → normalizer → canonical ProcessGraph.
"""
from typing import Any

from normalizer import to_process_graph
from schemas.process_graph import ProcessGraph

from assistants.graph_edits import apply_graph_edit


def process_assistant_apply(
    current: ProcessGraph | dict[str, Any],
    edit: dict[str, Any],
) -> ProcessGraph:
    """
    Apply assistant graph edit to current graph and return canonical ProcessGraph.
    current: existing ProcessGraph or raw dict (e.g. from YAML).
    edit: structured edit from Process Assistant (add_unit, remove_unit, connect, disconnect, no_edit).
    """
    if isinstance(current, ProcessGraph):
        raw = current.model_dump(by_alias=True)
    else:
        raw = dict(current)
    updated = apply_graph_edit(raw, edit)
    return to_process_graph(updated, format="dict")
