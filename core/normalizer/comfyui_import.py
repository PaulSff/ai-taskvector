"""
ComfyUI workflow import: map ComfyUI workflow JSON to canonical process graph dict.
"""
import copy
from typing import Any

from core.normalizer.shared import _ensure_list_connections
# Keys used for graph structure / identity; do not store in unit.params.
_COMFYUI_STRUCTURE_KEYS = frozenset({"id", "type", "pos", "class_type"})


def _comfyui_nodes_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract nodes array from ComfyUI workflow (top-level 'nodes')."""
    nodes = raw.get("nodes")
    return nodes if isinstance(nodes, list) else []


def _comfyui_links_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract links array from ComfyUI workflow (top-level 'links')."""
    links = raw.get("links")
    return links if isinstance(links, list) else []


def _comfyui_connections_from_links(
    links: list[dict[str, Any]], node_ids: set[str]
) -> list[dict[str, Any]]:
    """Build canonical connections from ComfyUI links. Preserves link type as connection_type for roundtrip."""
    out: list[dict[str, Any]] = []
    for lnk in links:
        if not isinstance(lnk, dict):
            continue
        oid = lnk.get("origin_id")
        tid = lnk.get("target_id")
        if oid is None or tid is None:
            continue
        oid = str(oid)
        tid = str(tid)
        if oid not in node_ids or tid not in node_ids or oid == tid:
            continue
        oslot = lnk.get("origin_slot")
        tslot = lnk.get("target_slot")
        entry: dict[str, Any] = {
            "from": oid,
            "to": tid,
            "from_port": str(oslot) if oslot is not None else "0",
            "to_port": str(tslot) if tslot is not None else "0",
        }
        link_type = lnk.get("type")
        if link_type is not None:
            if isinstance(link_type, (list, tuple)):
                entry["connection_type"] = ",".join(str(x) for x in link_type)
            else:
                entry["connection_type"] = str(link_type)
        out.append(entry)
    return out


def to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map ComfyUI workflow JSON to canonical process graph dict (environment_type, units, connections).
    Supports ComfyUI workflow format v1.0: nodes (id, type, pos, size, inputs, outputs, widgets_values),
    links (id, origin_id, origin_slot, target_id, target_slot). Node type = class_type (e.g. KSampler).
    """
    nodes = _comfyui_nodes_list(raw)
    links = _comfyui_links_list(raw)
    env_type = str((raw.get("environment_type") or raw.get("process_environment_type")) or "").strip()

    unit_ids: set[str] = set()
    units: list[dict[str, Any]] = []
    code_blocks: list[dict[str, Any]] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if nid is None:
            continue
        nid = str(nid)
        ntype = n.get("type") or n.get("class_type") or "Node"
        ntype = str(ntype)
        unit_ids.add(nid)

        # Preserve all ComfyUI node keys as params (size, flags, order, mode, properties, inputs, outputs, widgets_values, etc.)
        params: dict[str, Any] = {}
        for key, val in n.items():
            if key in _COMFYUI_STRUCTURE_KEYS or val is None:
                continue
            try:
                params[key] = copy.deepcopy(val) if isinstance(val, (dict, list)) else val
            except (TypeError, ValueError):
                params[key] = val
        # Export expects _comfy_* keys; set from top-level for backward compat
        if "_comfy_size" not in params and isinstance(params.get("size"), (list, tuple)) and len(params["size"]) >= 2:
            try:
                params["_comfy_size"] = [float(params["size"][0]), float(params["size"][1])]
            except (TypeError, ValueError):
                pass
        if "_comfy_flags" not in params and isinstance(params.get("flags"), dict):
            params["_comfy_flags"] = dict(params["flags"])
        if "_comfy_order" not in params and params.get("order") is not None:
            try:
                params["_comfy_order"] = int(params["order"])
            except (TypeError, ValueError):
                pass
        if "_comfy_mode" not in params and params.get("mode") is not None:
            try:
                params["_comfy_mode"] = int(params["mode"])
            except (TypeError, ValueError):
                pass
        if "_comfy_properties" not in params and isinstance(params.get("properties"), dict):
            params["_comfy_properties"] = dict(params["properties"])

        controllable = n.get("controllable")
        if controllable is None:
            controllable = True  # default True on import
        else:
            controllable = bool(controllable)
        unit_cfy: dict[str, Any] = {"id": nid, "type": ntype, "controllable": controllable, "params": params}
        cfy_name = n.get("title") or n.get("name")
        if isinstance(cfy_name, str) and cfy_name.strip():
            unit_cfy["name"] = cfy_name.strip()

        def _port_type_str(t: Any) -> str | None:
            if t is None:
                return None
            if isinstance(t, str):
                return t
            if isinstance(t, (list, tuple)) and t:
                return str(t[0])
            return str(t)

        inputs_raw = n.get("inputs")
        if isinstance(inputs_raw, list) and inputs_raw:
            unit_cfy["input_ports"] = [
                {"name": str(inp.get("name", f"input_{i}")), "type": _port_type_str(inp.get("type"))}
                for i, inp in enumerate(inputs_raw) if isinstance(inp, dict)
            ]
        outputs_raw = n.get("outputs")
        if isinstance(outputs_raw, list) and outputs_raw:
            unit_cfy["output_ports"] = [
                {"name": str(out.get("name", f"output_{i}")), "type": _port_type_str(out.get("type"))}
                for i, out in enumerate(outputs_raw) if isinstance(out, dict)
            ]
        units.append(unit_cfy)

        source = n.get("source") or n.get("code") or (params.get("source") if isinstance(params.get("source"), str) else None)
        if source and isinstance(source, str) and source.strip():
            code_blocks.append({
                "id": nid,
                "language": str(n.get("language", "python")),
                "source": source,
            })

    connections = _comfyui_connections_from_links(links, unit_ids)
    result: dict[str, Any] = {
        "environment_type": env_type,
        "units": units,
        "connections": _ensure_list_connections(connections),
    }
    if code_blocks:
        result["code_blocks"] = code_blocks

    layout: dict[str, dict[str, float]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if nid is None or str(nid) not in unit_ids:
            continue
        nid = str(nid)
        pos = n.get("pos")
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            try:
                layout[nid] = {"x": float(pos[0]), "y": float(pos[1])}
            except (TypeError, ValueError):
                pass
        elif isinstance(pos, dict) and ("0" in pos or 0 in pos):
            try:
                x = pos.get(0, pos.get("0", 0))
                y = pos.get(1, pos.get("1", 0))
                layout[nid] = {"x": float(x), "y": float(y)}
            except (TypeError, ValueError):
                pass
    if layout:
        result["layout"] = layout
    result["origin"] = {"comfyui": {}}
    return result
