"""
Compact diff between two graphs (units + connections). No dependency on assistants.
Used by the GraphDiff canonical unit and by GUI/workflow runners.
"""
from __future__ import annotations

from typing import Any

from core.schemas.process_graph import ProcessGraph


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


def graph_diff(
    prev: ProcessGraph | dict[str, Any] | None,
    current: ProcessGraph | dict[str, Any] | None,
) -> str:
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
