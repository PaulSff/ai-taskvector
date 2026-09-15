"""Shared: get current graph from inputs, apply edit via graph_edits, return outputs and state."""
from __future__ import annotations

from typing import cast

from core.schemas.graph_edit_api import GraphEdit
from core.schemas.primitives import Data, Output, RawProcessInput
from gui.components.workflow_tab.process_graph import ProcessGraph


def get_graph_from_inputs(inputs: Data) -> ProcessGraph:
    """Extract and normalize the current graph from direct or injected inputs."""
    from core.normalizer import to_process_graph

    raw_graph: object = inputs.get("graph")

    if raw_graph is None:
        data = inputs.get("data")

        if isinstance(data, dict):
            raw_graph = data.get("graph")

    if raw_graph is None:
        raw_graph = {}

    return to_process_graph(
        cast(RawProcessInput, raw_graph),
        format="dict",
    )


def apply_edit(
    inputs: Data,
    state: Data,
    edit: GraphEdit | Data,
) -> Output:
    from core.graph.graph_edits import GraphEdit, apply_graph_edit

    parsed_edit = (
        edit
        if isinstance(edit, GraphEdit)
        else GraphEdit.model_validate(edit)
    )

    current = get_graph_from_inputs(inputs)
    updated = apply_graph_edit(current, parsed_edit)

    return ({"graph": updated}, state)
