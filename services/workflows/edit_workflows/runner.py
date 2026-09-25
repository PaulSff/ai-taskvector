"""
Run a single graph edit through the unified workflow-edit runner.

Returns a normalized ProcessGraph for use by the GUI.
"""

from __future__ import annotations

from core.schemas.graph_edit_api import GraphEdit
from core.schemas.process_graph import ProcessGraph
from services.workflows.core_workflows import (
    run_apply_edits_inline,
    run_normalize_graph_inline,
)


async def apply_edit_via_workflow(
    graph: ProcessGraph,
    edit: GraphEdit,
) -> ProcessGraph:
    """
    Apply one graph edit through the unified edit runner.

    Raises ValueError when the edit fails or the resulting graph cannot
    be normalized.
    """
    updated_graph, edit_error = await run_apply_edits_inline(
        graph,
        [edit],
    )

    if edit_error:
        raise ValueError(edit_error)

    updated = updated_graph if updated_graph is not None else graph

    normalized_graph, normalize_error = await run_normalize_graph_inline(
        updated,
    )

    if normalize_error:
        raise ValueError(normalize_error)

    if normalized_graph is None:
        raise ValueError("NormalizeGraph: graph missing")

    return normalized_graph



__all__ = ["apply_edit_via_workflow"]
