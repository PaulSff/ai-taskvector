"""
Apply a list of graph edits to the ProcessGraph (batch application).

result = apply_workflow_edits(
    current=ProcessGraph(
        units=[],
        connections=[],
    ),
    edits=[],
)

assert isinstance(result["graph"], ProcessGraph)

The output shape is:
{
    "success": True,
    "graph": ProcessGraph(...),
    "error": None,
}
"""

from __future__ import annotations

from typing import get_args

from core.graph.graph_edits import apply_graph_edit
from core.graph.import_resolver import resolve_import_edits
from core.normalizer.runtime_detector import external_runtime_or_none
from core.schemas import ProcessGraph
from core.schemas.agent_node import RL_GYM_NODE_TYPE
from core.schemas.graph_edit_api import (
    ApplyWorkflowEditsResult,
    GraphEdit,
    GraphEditAction,
    GraphEditPipeline,
    GraphEditUnit,
    MultipleEditsSequential,
)

_GRAPH_EDIT_ACTIONS: frozenset[str] = frozenset(get_args(GraphEditAction))
RL_ORACLE_NODE_TYPE = "RLOracle"

# Generic error messages (no agents.prompts dependency)
_ERR_RLGYM_EXTERNAL = (
    "RLGym is for native (canonical) runtime only; use RLOracle for {runtime}."
)
_ERR_RLORACLE_NATIVE = (
    "RLOracle is for external runtimes only; use RLGym for native runtime."
)

_EDIT_PAYLOAD = GraphEditUnit | GraphEditPipeline


def _edit_payload(edit: GraphEdit) -> _EDIT_PAYLOAD | None:
    if edit.action == "add_unit":
        return edit.unit

    if edit.action == "replace_unit":
        return edit.replace_with

    if edit.action == "add_pipeline":
        return edit.pipeline

    return None


def _edit_adds_rlgym(edit: GraphEdit) -> bool:
    """True if this edit adds or replaces with an RLGym unit/pipeline."""
    payload = _edit_payload(edit)
    return payload is not None and payload.type == RL_GYM_NODE_TYPE



def _edit_adds_rloracle(edit: GraphEdit) -> bool:
    """True if this edit adds or replaces with an RLOracle unit/pipeline."""
    payload = _edit_payload(edit)
    return payload is not None and payload.type == RL_ORACLE_NODE_TYPE


def apply_workflow_edits(
    current: ProcessGraph | None,
    edits: MultipleEditsSequential,
    *,
    allowed_actions: frozenset[str] | None = None,
) -> ApplyWorkflowEditsResult:
    graph: ProcessGraph = (
        ProcessGraph() if current is None else current
    )

    for edit in edits.edits:
        act = edit.action

        if act not in _GRAPH_EDIT_ACTIONS:
            continue

        if act is None:
            continue

        if allowed_actions is not None and act not in allowed_actions:
            continue

        to_apply: list[GraphEdit]

        if act == "import_workflow":
            to_apply = resolve_import_edits([edit], graph)
        else:
            to_apply = [edit]

        for sub_edit in to_apply:
            if sub_edit.action is None:
                continue

            runtime = external_runtime_or_none(graph)

            if runtime is not None and _edit_adds_rlgym(sub_edit):
                return ApplyWorkflowEditsResult(
                    attempted=True,
                    success=False,
                    graph_after=graph,
                    error=_ERR_RLGYM_EXTERNAL.format(runtime=runtime),
                )

            if runtime is None and _edit_adds_rloracle(sub_edit):
                return ApplyWorkflowEditsResult(
                    attempted=True,
                    success=False,
                    graph_after=graph,
                    error=_ERR_RLORACLE_NATIVE,
                )

            try:
                graph = apply_graph_edit(graph, sub_edit)
            except (ValueError, TypeError) as ex:
                return ApplyWorkflowEditsResult(
                    attempted=True,
                    success=False,
                    graph_after=graph,
                    error=str(ex)[:500],
                )

    return ApplyWorkflowEditsResult(
        attempted=True,
        success=True,
        graph_after=graph,
        error=None,
    )
