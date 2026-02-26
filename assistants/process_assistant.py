"""
Process Assistant backend: apply graph edit → normalizer → canonical ProcessGraph.

Provides:
- process_assistant_apply: apply single edit
- graph_summary: LLM-friendly graph summary
- parse_workflow_edits: parse LLM output into edit list
- apply_workflow_edits: apply edit list, return (success, graph, error)
"""
from pathlib import Path
from typing import Any

from normalizer import to_process_graph
from schemas.process_graph import ProcessGraph

from assistants.graph_edits import apply_graph_edit
from assistants.llm_parsing import parse_json_blocks


def _port_names_for_type(type_name: str) -> tuple[list[str], list[str]]:
    """Return (input_port_names, output_port_names) for unit type from registry; empty lists if unknown."""
    try:
        from units.registry import get_unit_spec
        spec = get_unit_spec(type_name)
        if spec is None:
            return ([], [])
        in_names = [p[0] for p in spec.input_ports]
        out_names = [p[0] for p in spec.output_ports]
        return (in_names, out_names)
    except Exception:
        return ([], [])


def _origin_summary(origin: Any) -> dict[str, Any] | None:
    """Compact origin summary for LLM (runtime type, tab count)."""
    if origin is None:
        return None
    if hasattr(origin, "node_red") and origin.node_red is not None:
        tabs = getattr(origin.node_red, "tabs", None) or []
        return {"node_red": True, "tabs": len(tabs) if isinstance(tabs, list) else 0}
    if isinstance(origin, dict) and origin.get("node_red"):
        nr = origin["node_red"]
        tabs = nr.get("tabs", []) if isinstance(nr, dict) else []
        return {"node_red": True, "tabs": len(tabs) if isinstance(tabs, list) else 0}
    return None


def _code_blocks_summary(blocks: Any) -> list[dict[str, str]]:
    """Compact code blocks: id + language only (no source)."""
    if not blocks:
        return []
    out: list[dict[str, str]] = []
    for b in blocks if isinstance(blocks, list) else []:
        if isinstance(b, dict):
            out.append({"id": str(b.get("id", "?")), "language": str(b.get("language", "?"))})
        elif hasattr(b, "id") and hasattr(b, "language"):
            out.append({"id": str(b.id), "language": str(b.language)})
    return out


def graph_summary(current: ProcessGraph | dict[str, Any] | None) -> dict[str, Any]:
    """Reduce graph context to a small, LLM-friendly summary."""
    if current is None:
        return {"units": [], "connections": [], "environment_type": None}
    if isinstance(current, dict):
        units = current.get("units", []) or []
        conns = current.get("connections", []) or []
        unit_summary = []
        for u in units:
            if not isinstance(u, dict):
                continue
            uid = u.get("id")
            utype = u.get("type")
            in_names, out_names = _port_names_for_type(utype or "")
            entry: dict[str, Any] = {
                "id": uid,
                "type": utype,
                "controllable": bool(u.get("controllable", False)),
            }
            if in_names:
                entry["input_ports"] = in_names  # index i = name at position i
            if out_names:
                entry["output_ports"] = out_names
            unit_summary.append(entry)
        conn_summary = [
            {
                "from": c.get("from") or c.get("from_id"),
                "to": c.get("to") or c.get("to_id"),
                "from_port": str(c.get("from_port", "0")),
                "to_port": str(c.get("to_port", "0")),
            }
            for c in conns
            if isinstance(c, dict)
        ]
        env = current.get("environment_type")
        origin = _origin_summary(current.get("origin"))
        code_blocks = _code_blocks_summary(current.get("code_blocks"))
    else:
        unit_summary = []
        for u in current.units:
            in_names, out_names = _port_names_for_type(u.type)
            entry: dict[str, Any] = {
                "id": u.id,
                "type": u.type,
                "controllable": bool(u.controllable),
            }
            if in_names:
                entry["input_ports"] = in_names
            if out_names:
                entry["output_ports"] = out_names
            unit_summary.append(entry)
        conn_summary = [
            {"from": c.from_id, "to": c.to_id, "from_port": c.from_port, "to_port": c.to_port}
            for c in current.connections
        ]
        env = getattr(current.environment_type, "value", None) if hasattr(current, "environment_type") else None
        origin = _origin_summary(getattr(current, "origin", None))
        code_blocks = _code_blocks_summary(getattr(current, "code_blocks", None))
    result: dict[str, Any] = {
        "units": unit_summary,
        "connections": conn_summary,
    }
    if env is not None:
        result["environment_type"] = env
    if origin is not None:
        result["origin"] = origin
    if code_blocks:
        result["code_blocks"] = code_blocks
    return result


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
    *,
    rag_index_dir: str | Path | None = None,
    rag_embedding_model: str | None = None,
) -> dict[str, Any]:
    """
    Apply a list of graph edits sequentially.
    Supports import_unit and import_workflow when rag_index_dir is provided.
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

        # Resolve import_unit and import_workflow to concrete edits
        curr_dict = graph.model_dump(by_alias=True) if isinstance(graph, ProcessGraph) else dict(graph)
        if edit.get("action") in ("import_unit", "import_workflow") and (
            edit.get("action") != "import_unit" or rag_index_dir
        ):
            from assistants.import_resolver import resolve_import_edits

            resolved = resolve_import_edits(
                [edit],
                curr_dict,
                rag_index_dir=rag_index_dir,
                rag_embedding_model=rag_embedding_model,
            )
            to_apply = resolved
        else:
            to_apply = [edit]

        for sub_edit in to_apply:
            if not isinstance(sub_edit, dict) or sub_edit.get("action") in (None, "no_edit"):
                continue
            try:
                graph = process_assistant_apply(graph, sub_edit)
            except Exception as ex:
                return {
                    "success": False,
                    "graph": graph,
                    "error": str(ex)[:500],
                }

    return {"success": True, "graph": graph, "error": None}
