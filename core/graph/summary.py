"""
LLM-friendly graph summary. No dependency on assistants.
Used by ApplyEdits unit and by workflow designer / chat.
"""
from __future__ import annotations

from typing import Any

from core.schemas.process_graph import ProcessGraph

# Caps to avoid overwhelming the LLM (timeouts, distraction)
METADATA_STR_MAX = 400
COMMENTS_MAX = 8
COMMENT_INFO_MAX = 200
TODO_TASKS_MAX = 12


def _truncate(s: str, max_len: int) -> str:
    if not s or len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."


def _port_names_from_unit(u: Any) -> tuple[list[str], list[str]]:
    """Return (input_port_names, output_port_names) from graph unit."""
    in_raw = u.get("input_ports") if isinstance(u, dict) else getattr(u, "input_ports", None)
    out_raw = u.get("output_ports") if isinstance(u, dict) else getattr(u, "output_ports", None)
    in_list = in_raw if isinstance(in_raw, list) else []
    out_list = out_raw if isinstance(out_raw, list) else []
    in_names = [p.get("name", "") if isinstance(p, dict) else getattr(p, "name", "") for p in in_list]
    out_names = [p.get("name", "") if isinstance(p, dict) else getattr(p, "name", "") for p in out_list]
    return (in_names, out_names)


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


def _code_blocks_summary(
    blocks: Any,
    *,
    include_code_block_source: bool = False,
    include_source_for_unit_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Code blocks: id + language; optionally include source for all (when include_code_block_source)
    or only for unit ids in include_source_for_unit_ids (e.g. open review/add-code tasks)."""
    if not blocks:
        return []
    include_ids = set(include_source_for_unit_ids or []) if include_source_for_unit_ids else set()
    out: list[dict[str, Any]] = []
    for b in blocks if isinstance(blocks, list) else []:
        bid = ""
        lang = "?"
        src = None
        if isinstance(b, dict):
            bid = str(b.get("id", "?"))
            lang = str(b.get("language", "?"))
            if include_code_block_source or bid in include_ids:
                src = b.get("source")
        elif hasattr(b, "id") and hasattr(b, "language"):
            bid = str(b.id)
            lang = str(b.language)
            if include_code_block_source or bid in include_ids:
                src = getattr(b, "source", None)
        entry: dict[str, Any] = {"id": bid, "language": lang}
        if src is not None and str(src).strip():
            entry["source"] = str(src).strip()
        out.append(entry)
    return out


def graph_summary(
    current: ProcessGraph | dict[str, Any] | None,
    *,
    include_code_block_source: bool = False,
    include_source_for_unit_ids: list[str] | None = None,
    include_structure: bool = True,
) -> dict[str, Any]:
    """Reduce graph context to a small, LLM-friendly summary.
    When include_code_block_source is True, code_blocks in the summary include source for all.
    When include_source_for_unit_ids is set, code_blocks include source only for those unit ids (e.g. open tasks).
    When include_structure is False, omit units, connections, code blocks, metadata, and origin context;
    keep only comments and todo_list (for analyst-style prompts)."""
    if current is None:
        if include_structure:
            return {"units": [], "connections": [], "environment_type": None}
        return {"units": [], "connections": []}
    if isinstance(current, dict):
        comments_raw = current.get("comments") or []
        todo_list_raw = current.get("todo_list")
        if include_structure:
            units = current.get("units", []) or []
            conns = current.get("connections", []) or []
            unit_summary: list[dict[str, Any]] = []
            for u in units:
                if not isinstance(u, dict):
                    continue
                uid = u.get("id")
                utype = u.get("type")
                in_names, out_names = _port_names_from_unit(u)
                params = u.get("params")
                if not isinstance(params, dict):
                    params = {}
                entry: dict[str, Any] = {
                    "id": uid,
                    "type": utype,
                    "controllable": bool(u.get("controllable", False)),
                    "params": dict(params),
                    "input_ports": in_names,
                    "output_ports": out_names,
                }
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
            environments = current.get("environments")
            origin = _origin_summary(current.get("origin"))
            origin_format = current.get("origin_format")
            code_blocks = _code_blocks_summary(
                current.get("code_blocks"),
                include_code_block_source=include_code_block_source,
                include_source_for_unit_ids=include_source_for_unit_ids,
            )
            metadata = current.get("metadata")
        else:
            unit_summary = []
            conn_summary = []
            env = None
            environments = None
            origin = None
            origin_format = None
            code_blocks = []
            metadata = None
    else:
        comments_raw = getattr(current, "comments", None) or []
        todo_list_raw = getattr(current, "todo_list", None)
        if include_structure:
            unit_summary = []
            for u in current.units:
                in_names, out_names = _port_names_from_unit(u)
                params = getattr(u, "params", None)
                if not isinstance(params, dict):
                    params = {}
                unit_summary.append({
                    "id": u.id,
                    "type": u.type,
                    "controllable": bool(u.controllable),
                    "params": dict(params),
                    "input_ports": in_names,
                    "output_ports": out_names,
                })
            conn_summary = [
                {"from": c.from_id, "to": c.to_id, "from_port": c.from_port, "to_port": c.to_port}
                for c in current.connections
            ]
            env = getattr(current.environment_type, "value", None) if hasattr(current, "environment_type") else None
            environments = getattr(current, "environments", None)
            origin = _origin_summary(getattr(current, "origin", None))
            origin_format = getattr(current, "origin_format", None)
            code_blocks = _code_blocks_summary(
                getattr(current, "code_blocks", None),
                include_code_block_source=include_code_block_source,
                include_source_for_unit_ids=include_source_for_unit_ids,
            )
            metadata = getattr(current, "metadata", None)
        else:
            unit_summary = []
            conn_summary = []
            env = None
            environments = None
            origin = None
            origin_format = None
            code_blocks = []
            metadata = None
    comments_summary: list[dict[str, Any]] = []
    for c in comments_raw:
        if isinstance(c, dict):
            info = c.get("info") or ""
            comments_summary.append({
                "id": c.get("id"),
                "info": _truncate(info if isinstance(info, str) else str(info), COMMENT_INFO_MAX),
                "commenter": c.get("commenter", ""),
                "created_at": c.get("created_at", ""),
            })
        else:
            info = getattr(c, "info", "") or ""
            comments_summary.append({
                "id": getattr(c, "id", None),
                "info": _truncate(info if isinstance(info, str) else str(info), COMMENT_INFO_MAX),
                "commenter": getattr(c, "commenter", "") or "",
                "created_at": getattr(c, "created_at", "") or "",
            })
    if len(comments_summary) > COMMENTS_MAX:
        comments_summary = comments_summary[-COMMENTS_MAX:]
    result: dict[str, Any] = {
        "units": unit_summary,
        "connections": conn_summary,
    }
    if include_structure:
        if env is not None:
            result["environment_type"] = env
        if environments is not None and isinstance(environments, list):
            result["environments"] = environments
        if origin is not None:
            result["origin"] = origin
        if origin_format is not None:
            result["origin_format"] = origin_format
        if code_blocks:
            result["code_blocks"] = code_blocks
    if include_structure and metadata and isinstance(metadata, dict) and metadata:
        capped: dict[str, Any] = {}
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, str):
                if v.strip():
                    capped[k] = _truncate(v, METADATA_STR_MAX)
            else:
                capped[k] = v
        if capped:
            result["metadata"] = capped
    if comments_summary:
        result["comments"] = comments_summary
    if todo_list_raw is not None:
        if isinstance(todo_list_raw, dict):
            tasks = todo_list_raw.get("tasks") or []
            tasks = [t for t in tasks if isinstance(t, dict)][:TODO_TASKS_MAX]
            result["todo_list"] = {
                "id": todo_list_raw.get("id", "todo_list_default"),
                "title": todo_list_raw.get("title"),
                "tasks": [
                    {"id": t.get("id"), "text": t.get("text"), "completed": t.get("completed", False), "created_at": t.get("created_at", "")}
                    for t in tasks
                ],
            }
        else:
            tasks = (getattr(todo_list_raw, "tasks", None) or [])[:TODO_TASKS_MAX]
            result["todo_list"] = {
                "id": getattr(todo_list_raw, "id", "todo_list_default"),
                "title": getattr(todo_list_raw, "title", None),
                "tasks": [
                    {"id": getattr(t, "id", ""), "text": getattr(t, "text", ""), "completed": getattr(t, "completed", False), "created_at": getattr(t, "created_at", "")}
                    for t in tasks
                ],
            }
    return result
