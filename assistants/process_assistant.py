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


def _units_set(g: dict[str, Any]) -> set[tuple[str, str]]:
    """(id, type) for each unit."""
    out: set[tuple[str, str]] = set()
    for u in (g.get("units") or []):
        if isinstance(u, dict):
            uid = u.get("id") or "?"
            utype = u.get("type") or "?"
            out.add((str(uid), str(utype)))
    return out


def _conns_set(g: dict[str, Any]) -> set[tuple[str, str]]:
    """(from, to) for each connection."""
    out: set[tuple[str, str]] = set()
    for c in (g.get("connections") or []):
        if isinstance(c, dict):
            fr = c.get("from") or c.get("from_id") or "?"
            to = c.get("to") or c.get("to_id") or "?"
            out.add((str(fr), str(to)))
    return out


def graph_diff(prev: ProcessGraph | dict[str, Any] | None, current: ProcessGraph | dict[str, Any] | None) -> str:
    """
    Produce a compact changelog of what changed from prev to current.
    Returns empty string if either is None or no changes.
    """
    if prev is None or current is None:
        return ""
    prev_d = prev.model_dump(by_alias=True) if isinstance(prev, ProcessGraph) else dict(prev)
    curr_d = current.model_dump(by_alias=True) if isinstance(current, ProcessGraph) else dict(current)
    prev_units = _units_set(prev_d)
    curr_units = _units_set(curr_d)
    prev_conns = _conns_set(prev_d)
    curr_conns = _conns_set(curr_d)
    parts: list[str] = []
    added_units = curr_units - prev_units
    if added_units:
        parts.append("added " + ", ".join(f"{uid} ({utype})" for uid, utype in sorted(added_units)))
    removed_units = prev_units - curr_units
    if removed_units:
        parts.append("removed " + ", ".join(uid for uid, _ in sorted(removed_units)))
    added_conns = curr_conns - prev_conns
    if added_conns:
        parts.append("connected " + ", ".join(f"{a}->{b}" for a, b in sorted(added_conns)))
    removed_conns = prev_conns - curr_conns
    if removed_conns:
        parts.append("disconnected " + ", ".join(f"{a}->{b}" for a, b in sorted(removed_conns)))
    return "; ".join(parts) if parts else ""


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
