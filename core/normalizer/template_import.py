"""
Template-style import: map template/generic dict to canonical process graph dict.
Accepts blocks/units and links/connections; used by IDAES and generic templates.
"""
from typing import Any

from core.normalizer.shared import _ensure_list_connections


def to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map template-style dict to canonical process graph dict.
    Accepts: blocks (list of {id, type, params?, controllable?}) and links (list of {from, to}),
    or canonical-like units/connections. Optional template_type and environment_type.
    """
    env_type = str((raw.get("environment_type") or raw.get("process_environment_type")) or "").strip()
    blocks = raw.get("blocks") or raw.get("units")
    links = raw.get("links") or raw.get("connections")
    if blocks is None:
        blocks = []
    if links is None:
        links = []
    units: list[dict[str, Any]] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        uid = b.get("id") or b.get("name")
        if uid is None:
            continue
        utype = b.get("type") or b.get("unitType") or b.get("blockType")
        if utype is None:
            continue
        unit_tpl: dict[str, Any] = {
            "id": str(uid),
            "type": str(utype),
            "controllable": bool(b.get("controllable", b.get("is_control", True))),
            "params": dict(b.get("params") or b.get("parameters") or {}),
        }
        tpl_name = b.get("name")
        if isinstance(tpl_name, str) and tpl_name.strip():
            unit_tpl["name"] = tpl_name.strip()
        units.append(unit_tpl)
    connections = _ensure_list_connections(links)
    return {
        "environment_type": env_type,
        "units": units,
        "connections": connections,
    }
