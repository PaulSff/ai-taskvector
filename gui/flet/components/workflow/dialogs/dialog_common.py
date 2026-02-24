"""
Shared helpers for process-graph dialogs (add node, add/remove link).
Converts ProcessGraph to/from dict shape expected by graph_edits.
"""
from __future__ import annotations

from schemas.process_graph import ProcessGraph


def graph_to_dict(g: ProcessGraph) -> dict:
    """ProcessGraph to dict for graph_edits (connections use 'from'/'to'/'from_port'/'to_port')."""
    d = g.model_dump()
    conns = []
    for c in d.get("connections", []):
        conns.append({
            "from": c.get("from") or c.get("from_id"),
            "to": c.get("to") or c.get("to_id"),
            "from_port": str(c.get("from_port", "0")),
            "to_port": str(c.get("to_port", "0")),
        })
    d["connections"] = conns
    return d


def dict_to_graph(d: dict) -> ProcessGraph:
    """Dict from graph_edits back to ProcessGraph."""
    return ProcessGraph.model_validate(d)
