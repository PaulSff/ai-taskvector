"""
Load canonical pipeline workflows from JSON and merge them into a graph with interface wiring.

Pipeline type (e.g. LLMSet) maps to a workflow file. The file defines topology (units + connections)
and a pipeline_interface: observation_inputs, action_output, params_unit_id. No topology is built
in code; we import the template and wire observation_source_ids → observation_inputs,
action_output → action_target_ids, and apply params to params_unit_id.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from units.registry import get_unit_spec

_CORE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _CORE_ROOT.parent.parent


def load_pipeline_template(pipeline_type: str, base_path: Path | None = None) -> dict[str, Any] | None:
    """
    Load pipeline template JSON for the given type. Path is taken from the unit registry
    (UnitSpec.template_path) for that pipeline type. Returns dict with keys:
    units, connections, pipeline_interface (observation_inputs, action_output, params_unit_id).
    Returns None if file missing or invalid.
    """
    spec = get_unit_spec(pipeline_type)
    if not spec or not spec.pipeline or not spec.template_path:
        return None
    rel = spec.template_path
    base = base_path or _REPO_ROOT
    path = (base / rel).resolve()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    units = data.get("units")
    connections = data.get("connections")
    if not isinstance(units, list) or not isinstance(connections, list):
        return None
    interface = data.get("pipeline_interface")
    if not isinstance(interface, dict):
        return None
    obs_in = interface.get("observation_inputs")
    action_out = interface.get("action_output")
    params_uid = interface.get("params_unit_id")
    if not isinstance(obs_in, list) or not isinstance(action_out, dict) or not params_uid:
        return None
    return {
        "units": units,
        "connections": connections,
        "observation_inputs": obs_in,
        "action_output": action_out,
        "params_unit_id": str(params_uid),
    }


def merge_pipeline_into_graph(
    units: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    template: dict[str, Any],
    pipeline_id: str,
    params: dict[str, Any],
    observation_source_ids: list[str],
    action_target_ids: list[str],
    existing_ids: set[str] | None = None,
) -> None:
    """
    Merge the pipeline template into the current graph (mutates units and connections).
    - Template unit IDs are prefixed with pipeline_id + "_", except params_unit_id which becomes pipeline_id.
    - Params (excluding observation_source_ids, action_target_ids) are applied to the params unit.
    - Wiring: observation_source_ids[i] → observation_inputs[i]; action_output → each action_target_id.
    """
    existing = existing_ids or {u.get("id") for u in units if isinstance(u, dict) and u.get("id")}
    obs_inputs = template.get("observation_inputs") or []
    action_out = template.get("action_output") or {}
    params_uid = template.get("params_unit_id") or ""
    out_unit_id = str(action_out.get("unit_id", ""))
    out_port = str(action_out.get("port", "edits"))
    params_override = {k: v for k, v in (params or {}).items() if k not in ("observation_source_ids", "action_target_ids")}

    id_map: dict[str, str] = {}
    for u in template.get("units") or []:
        if not isinstance(u, dict):
            continue
        old_id = str(u.get("id", ""))
        if old_id == params_uid:
            new_id = pipeline_id
        else:
            new_id = f"{pipeline_id}_{old_id}"
        if new_id in existing:
            n = 1
            while f"{new_id}_{n}" in existing:
                n += 1
            new_id = f"{new_id}_{n}"
        id_map[old_id] = new_id
        existing.add(new_id)
        new_u = dict(u)
        new_u["id"] = new_id
        if new_id == pipeline_id and params_override:
            new_u["params"] = {**(new_u.get("params") or {}), **params_override}
        units.append(new_u)

    for c in template.get("connections") or []:
        if not isinstance(c, dict):
            continue
        fr = c.get("from") or c.get("from_id")
        to = c.get("to") or c.get("to_id")
        if fr is None or to is None:
            continue
        fr = id_map.get(str(fr), str(fr))
        to = id_map.get(str(to), str(to))
        if fr in existing and to in existing:
            conn = {"from": fr, "to": to}
            conn["from_port"] = str(c.get("from_port", "0"))
            conn["to_port"] = str(c.get("to_port", "0"))
            connections.append(conn)

    for i, sid in enumerate(observation_source_ids):
        if i >= len(obs_inputs) or sid not in existing:
            continue
        inp = obs_inputs[i] if isinstance(obs_inputs[i], dict) else {}
        tuid = id_map.get(str(inp.get("unit_id", "")), str(inp.get("unit_id", "")))
        port = str(inp.get("port", str(i)))
        if tuid in existing:
            connections.append({"from": sid, "to": tuid, "from_port": "0", "to_port": port})

    mapped_out_id = id_map.get(out_unit_id, out_unit_id)
    if mapped_out_id in existing:
        for tid in action_target_ids:
            if tid in existing:
                connections.append({"from": mapped_out_id, "to": tid, "from_port": out_port, "to_port": "0"})
