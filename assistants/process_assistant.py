"""
Process Assistant backend: apply graph edit → normalizer → canonical ProcessGraph.

Provides:
- process_assistant_apply: apply single edit
- graph_summary: LLM-friendly graph summary
- parse_workflow_edits: parse LLM output into edit list
- apply_workflow_edits: apply edit list, return (success, graph, error)
"""
from typing import Any

from normalizer import to_process_graph
from schemas.process_graph import ProcessGraph

from assistants.graph_edits import apply_graph_edit
from assistants.llm_parsing import parse_json_blocks


def graph_summary(current: ProcessGraph | dict[str, Any] | None) -> dict[str, Any]:
    """Reduce graph context to a small, LLM-friendly summary."""
    if current is None:
        return {"units": [], "connections": []}
    if isinstance(current, dict):
        units = current.get("units", []) or []
        conns = current.get("connections", []) or []
        unit_summary = [
            {"id": u.get("id"), "type": u.get("type"), "controllable": bool(u.get("controllable", False))}
            for u in units
            if isinstance(u, dict)
        ]
        conn_summary = [
            {"from": c.get("from") or c.get("from_id"), "to": c.get("to") or c.get("to_id")}
            for c in conns
            if isinstance(c, dict)
        ]
        return {"units": unit_summary, "connections": conn_summary}
    if isinstance(current, ProcessGraph):
        return {
            "units": [{"id": u.id, "type": u.type, "controllable": bool(u.controllable)} for u in current.units],
            "connections": [{"from": c.from_id, "to": c.to_id} for c in current.connections],
        }
    return {"units": [], "connections": []}


def parse_workflow_edits(content: str) -> list[dict[str, Any]] | dict[str, str]:
    """
    Parse LLM content into a list of graph edits.
    Returns list of edit dicts, or {parse_error: str} if fenced JSON was present but all blocks failed.
    """
    parsed = parse_json_blocks(content)
    if isinstance(parsed, dict):
        return parsed
    return _normalize_parsed_to_edits(parsed)


def _normalize_parsed_to_edits(parsed_blocks: list[Any]) -> list[dict[str, Any]]:
    """Convert parsed JSON blocks to flat list of edit dicts."""
    edits: list[dict[str, Any]] = []
    for parsed in parsed_blocks:
        if isinstance(parsed, list):
            edits.extend([e for e in parsed if isinstance(e, dict)])
        elif isinstance(parsed, dict):
            if parsed.get("action"):
                edits.append(parsed)
            elif isinstance(parsed.get("edits"), list):
                edits.extend([e for e in parsed["edits"] if isinstance(e, dict)])
    return edits


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
    Apply a list of graph edits sequentially.
    Returns dict: {success: bool, graph: ProcessGraph | dict, error: str | None}
    """
    if current is None:
        current = {"units": [], "connections": []}
    graph: ProcessGraph | dict = current if isinstance(current, ProcessGraph) else dict(current)

    for edit in edits:
        if not isinstance(edit, dict):
            continue
        if edit.get("action") in (None, "no_edit"):
            continue
        try:
            graph = process_assistant_apply(graph, edit)
        except Exception as ex:
            return {
                "success": False,
                "graph": graph,
                "error": str(ex)[:500],
            }

    return {"success": True, "graph": graph, "error": None}
