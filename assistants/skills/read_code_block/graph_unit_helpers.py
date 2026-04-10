"""Graph helpers for read_code_block follow-up (units vs code_blocks)."""
from __future__ import annotations

from typing import Any


def code_block_ids_on_graph(graph_dict: dict[str, Any]) -> set[str]:
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


def canonical_unit_type_name(raw: str | None) -> str:
    from core.normalizer.shared import _canonical_unit_type

    if not raw:
        return ""
    return _canonical_unit_type(str(raw).strip())


def unit_types_missing_code_blocks(graph_dict: dict[str, Any], unit_ids: list[str]) -> list[str]:
    """Registry types for requested unit ids that have no graph code_block (ordered, unique)."""
    cb_ids = code_block_ids_on_graph(graph_dict)
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
        t = canonical_unit_type_name(u.get("type"))
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered
