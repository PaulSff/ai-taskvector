"""Pure graph lookups: code block ids, unit rows by id, canonical types missing on-graph code blocks."""
from __future__ import annotations

from typing import Any

from core.normalizer.shared import _canonical_unit_type


def code_block_ids_from_graph(graph_dict: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    cbs = graph_dict.get("code_blocks") or []
    if not isinstance(cbs, list):
        return out
    for b in cbs:
        if isinstance(b, dict):
            bid = b.get("id")
            if bid is not None:
                s = str(bid).strip()
                if s:
                    out.add(s)
    return out


def canonical_types_without_code_block(graph_dict: dict[str, Any], unit_ids: list[str]) -> list[str]:
    """Ordered unique canonical unit types for requested ids that exist on the graph but have no code_block id."""
    cb_ids = code_block_ids_from_graph(graph_dict)
    units = graph_dict.get("units") or []
    if not isinstance(units, list):
        return []
    by_id: dict[str, dict[str, Any]] = {}
    for u in units:
        if isinstance(u, dict) and u.get("id") is not None:
            by_id[str(u["id"]).strip()] = u
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_id in unit_ids:
        uid = str(raw_id or "").strip()
        if not uid:
            continue
        if uid in cb_ids:
            continue
        u = by_id.get(uid)
        if not u:
            continue
        raw_type = str(u.get("type") or "").strip()
        t = _canonical_unit_type(raw_type) if raw_type else ""
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def lookup_graph_units_data(graph_dict: dict[str, Any], unit_ids: list[str]) -> dict[str, Any]:
    """
    Structured lookup for workflows. ``graph_dict`` should already be a canonical dict
    (e.g. after ``NormalizeGraph``); this does not run ``to_process_graph``.

    Returns keys: ``unit_ids``, ``has_graph``, ``code_block_ids``, ``units``,
    ``canonical_types_without_code_block``, ``needs_implementation_links`` (bool).
    """
    cb_ids = code_block_ids_from_graph(graph_dict)
    units = graph_dict.get("units") or []
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(units, list):
        for u in units:
            if isinstance(u, dict) and u.get("id") is not None:
                by_id[str(u["id"]).strip()] = u

    rows: list[dict[str, Any]] = []
    for uid in unit_ids:
        u = by_id.get(uid)
        found = u is not None
        raw_type = str(u.get("type", "")).strip() if isinstance(u, dict) else ""
        canon = _canonical_unit_type(raw_type) if raw_type else ""
        has_cb = uid in cb_ids
        rows.append(
            {
                "unit_id": uid,
                "found": found,
                "has_code_block": has_cb,
                "unit_type_raw": raw_type,
                "unit_type_canonical": canon,
            }
        )

    missing = canonical_types_without_code_block(graph_dict, unit_ids)
    has_graph = bool(graph_dict) and isinstance(graph_dict.get("units"), list)

    return {
        "unit_ids": list(unit_ids),
        "has_graph": has_graph,
        "code_block_ids": sorted(cb_ids),
        "units": rows,
        "canonical_types_without_code_block": missing,
        "needs_implementation_links": bool(missing),
    }


__all__ = [
    "code_block_ids_from_graph",
    "canonical_types_without_code_block",
    "lookup_graph_units_data",
]
