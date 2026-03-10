"""
Process Assistant backend: apply graph edit → normalizer → canonical ProcessGraph.

Provides:
- process_assistant_apply: apply single graph edit
- graph_summary: LLM-friendly graph summary (from core.graph.summary)
- apply_workflow_edits: apply list of graph edits (from core.graph.batch_edits)

parse_action_blocks / parse_workflow_edits live in units.canonical.process_agent.action_blocks.
"""
from typing import Any

from core.normalizer import to_process_graph
from core.schemas.process_graph import ProcessGraph

from core.graph.graph_edits import apply_graph_edit
from core.graph.summary import graph_summary
from core.graph.batch_edits import apply_workflow_edits as _apply_workflow_edits

# Re-export from ProcessAgent unit for backward compat (GUI, assistants API).
from units.canonical.process_agent.action_blocks import parse_action_blocks, parse_workflow_edits


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


def apply_workflow_edits(
    current: ProcessGraph | dict[str, Any] | None,
    edits: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Apply a list of graph edits sequentially. Delegates to core.graph.batch_edits.
    Accepts ProcessGraph or dict; returns dict with graph as dict.
    """
    if current is None:
        graph_dict: dict[str, Any] | None = None
    elif hasattr(current, "model_dump"):
        graph_dict = current.model_dump(by_alias=True)
    else:
        graph_dict = dict(current) if isinstance(current, dict) else None
    return _apply_workflow_edits(graph_dict, edits)
