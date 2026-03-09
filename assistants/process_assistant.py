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
from normalizer.runtime_detector import external_runtime_or_none
from schemas.agent_node import RL_GYM_NODE_TYPE
from schemas.process_graph import ProcessGraph

from assistants.edit_workflow_runner import run_edit_flow
from assistants.graph_edits import apply_graph_edit
from assistants.llm_parsing import parse_json_blocks
from assistants.prompts import (
    WORKFLOW_DESIGNER_RLGYM_EXTERNAL_RUNTIME_ERROR,
    WORKFLOW_DESIGNER_RLORACLE_NATIVE_RUNTIME_ERROR,
)

# Caps for graph_summary to avoid overwhelming the Workflow Designer LLM (timeouts, distraction)
METADATA_STR_MAX = 400
COMMENTS_MAX = 8
COMMENT_INFO_MAX = 200
TODO_TASKS_MAX = 12


def _truncate(s: str, max_len: int) -> str:
    if not s or len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."


def _port_names_from_unit(u: Any) -> tuple[list[str], list[str]]:
    """Return (input_port_names, output_port_names) from graph unit (Registry → Graph → Summary)."""
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
            in_names, out_names = _port_names_from_unit(u)
            entry: dict[str, Any] = {
                "id": uid,
                "type": utype,
                "controllable": bool(u.get("controllable", False)),
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
        code_blocks = _code_blocks_summary(current.get("code_blocks"))
        metadata = current.get("metadata")
        comments_raw = current.get("comments") or []
        todo_list_raw = current.get("todo_list")
    else:
        unit_summary = []
        for u in current.units:
            in_names, out_names = _port_names_from_unit(u)
            unit_summary.append({
                "id": u.id,
                "type": u.type,
                "controllable": bool(u.controllable),
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
        code_blocks = _code_blocks_summary(getattr(current, "code_blocks", None))
        metadata = getattr(current, "metadata", None)
        comments_raw = getattr(current, "comments", None) or []
        todo_list_raw = getattr(current, "todo_list", None)
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
    # Keep only the most recent comments to limit context size
    if len(comments_summary) > COMMENTS_MAX:
        comments_summary = comments_summary[-COMMENTS_MAX:]
    result: dict[str, Any] = {
        "units": unit_summary,
        "connections": conn_summary,
    }
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
    if metadata and isinstance(metadata, dict) and metadata:
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


def parse_workflow_edits(content: str) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Parse LLM content into a list of graph edits and optional request_unit_specs.
    Returns:
      - list of edit dicts (when no request_unit_specs),
      - dict with "edits" and "request_unit_specs" (list of unit ids) when that action was present,
      - or {parse_error: str} if fenced JSON was present but all blocks failed.
    """
    parsed = parse_json_blocks(content)
    if isinstance(parsed, dict):
        return parsed
    return _normalize_parsed_to_edits(parsed)


def _normalize_parsed_to_edits(parsed_blocks: list[Any]) -> list[dict[str, Any]] | dict[str, Any]:
    """Convert parsed JSON blocks to flat list of edit dicts; extract request_unit_specs, request_file_content, rag_search separately."""
    edits: list[dict[str, Any]] = []
    request_unit_specs: list[str] = []
    request_file_content_paths: list[str] = []
    rag_search_query: str | None = None
    rag_search_max_results: int | None = None
    read_code_block_ids: list[str] = []

    def collect_one(obj: dict[str, Any]) -> None:
        nonlocal rag_search_query, rag_search_max_results, read_code_block_ids
        if obj.get("action") == "request_unit_specs":
            uids = obj.get("unit_ids")
            if isinstance(uids, list):
                for x in uids:
                    if isinstance(x, str) and x.strip():
                        request_unit_specs.append(x.strip())
            elif isinstance(uids, str) and uids.strip():
                request_unit_specs.append(uids.strip())
            return
        if obj.get("action") == "request_file_content":
            path = obj.get("path")
            if isinstance(path, str) and path.strip():
                request_file_content_paths.append(path.strip())
            return
        if obj.get("action") == "search":
            q = obj.get("what") or obj.get("query") or obj.get("q")
            if isinstance(q, str) and q.strip():
                rag_search_query = q.strip()
            mr = obj.get("max_results")
            if mr is not None:
                try:
                    n = int(mr)
                    if n >= 1:
                        rag_search_max_results = min(50, n)
                except (TypeError, ValueError):
                    pass
            return
        if obj.get("action") == "read_code_block":
            bid = obj.get("id")
            if isinstance(bid, str) and bid.strip():
                read_code_block_ids.append(bid.strip())
            elif isinstance(bid, list):
                for x in bid:
                    if isinstance(x, str) and x.strip():
                        read_code_block_ids.append(x.strip())
            return
        if obj.get("action"):
            edits.append(obj)
        elif isinstance(obj.get("edits"), list):
            for e in obj["edits"]:
                if isinstance(e, dict):
                    collect_one(e)

    for parsed in parsed_blocks:
        if isinstance(parsed, list):
            for e in parsed:
                if isinstance(e, dict):
                    collect_one(e)
        elif isinstance(parsed, dict):
            collect_one(parsed)

    if request_unit_specs or request_file_content_paths or rag_search_query or read_code_block_ids:
        out: dict[str, Any] = {"edits": edits}
        if request_unit_specs:
            out["request_unit_specs"] = list(dict.fromkeys(request_unit_specs))
        if request_file_content_paths:
            out["request_file_content"] = list(dict.fromkeys(request_file_content_paths))
        if rag_search_query:
            out["rag_search"] = rag_search_query
            if rag_search_max_results is not None:
                out["rag_search_max_results"] = rag_search_max_results
        if read_code_block_ids:
            out["read_code_block_ids"] = list(dict.fromkeys(read_code_block_ids))
        return out
    return edits


def process_assistant_apply(
    current: ProcessGraph | dict[str, Any],
    edit: dict[str, Any],
) -> ProcessGraph:
    """
    Apply assistant graph edit to current graph and return canonical ProcessGraph.
    Runs the corresponding edit workflow (Inject -> edit unit) when available; otherwise applies edit directly.
    current: existing ProcessGraph or raw dict (e.g. from YAML).
    edit: structured edit from Process Assistant (add_unit, remove_unit, connect, disconnect, no_edit).
    """
    if isinstance(current, ProcessGraph):
        raw = current.model_dump(by_alias=True)
    else:
        raw = dict(current)
    updated = run_edit_flow(raw, edit)
    return to_process_graph(updated, format="dict")


RL_ORACLE_NODE_TYPE = "RLOracle"


def _edit_adds_rlgym(edit: dict[str, Any]) -> bool:
    """True if this edit would add or replace with an RLGym unit (native runtime only)."""
    if not isinstance(edit, dict):
        return False
    action = edit.get("action")
    if action == "add_unit":
        unit = edit.get("unit") or {}
        return (unit.get("type") or "").strip() == RL_GYM_NODE_TYPE
    if action == "replace_unit":
        repl = edit.get("replace_with") or {}
        return (repl.get("type") or "").strip() == RL_GYM_NODE_TYPE
    if action == "add_pipeline":
        pipeline = edit.get("pipeline") or {}
        return (pipeline.get("type") or "").strip() == RL_GYM_NODE_TYPE
    return False


def _edit_adds_rloracle(edit: dict[str, Any]) -> bool:
    """True if this edit would add or replace with an RLOracle unit (external runtime only)."""
    if not isinstance(edit, dict):
        return False
    action = edit.get("action")
    if action == "add_unit":
        unit = edit.get("unit") or {}
        return (unit.get("type") or "").strip() == RL_ORACLE_NODE_TYPE
    if action == "replace_unit":
        repl = edit.get("replace_with") or {}
        return (repl.get("type") or "").strip() == RL_ORACLE_NODE_TYPE
    if action == "add_pipeline":
        pipeline = edit.get("pipeline") or {}
        return (pipeline.get("type") or "").strip() == RL_ORACLE_NODE_TYPE
    return False


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
    Validates runtime: RLGym rejected on Node-RED/n8n; RLOracle rejected on native (canonical).
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
            # Reject RLGym on external runtimes; model should use RLOracle
            runtime = external_runtime_or_none(graph)
            if runtime is not None and _edit_adds_rlgym(sub_edit):
                return {
                    "success": False,
                    "graph": graph,
                    "error": WORKFLOW_DESIGNER_RLGYM_EXTERNAL_RUNTIME_ERROR.format(runtime=runtime),
                }
            # Reject RLOracle on native (canonical) runtime; model should use RLGym
            if runtime is None and _edit_adds_rloracle(sub_edit):
                return {
                    "success": False,
                    "graph": graph,
                    "error": WORKFLOW_DESIGNER_RLORACLE_NATIVE_RUNTIME_ERROR,
                }
            try:
                graph = process_assistant_apply(graph, sub_edit)
            except Exception as ex:
                return {
                    "success": False,
                    "graph": graph,
                    "error": str(ex)[:500],
                }

    return {"success": True, "graph": graph, "error": None}
