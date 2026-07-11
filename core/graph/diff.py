"""
graph_diff(prev, current) format options:
    - format="str" (default) returns a semicolon-separated string;
    - format="array" returns list[str]

If prev is None or current is None, it returns "".
Otherwise, it builds a list of clause strings and returns "; ".join(clauses).
A clause is included only if that category difference is detected.

Ordering is the order implemented in the function:
 1. environment_type clause (optional), Format: `environment_type: {prev_value}->{curr_value}`
 2. environments clause (optional),  Format: `environments changed`
 3. top-level units/connections clause(s) (always considered, but only included if there’s a diff), subformats:
    - `added {N} units: {uid1} ({type1}), {uid2} ({type2})...`
    - `removed {N} units: {id1}, {id2}, ...`
    - `updated units: {id1}, {id2}, ...`
    - `connected {N}: {sig1}, {sig2}, ...`
    - `disconnected {N}: {sig1}, {sig2}, ...`
 4. code_blocks clause(s), subformats:
    - `added code_blocks: {id1}, {id2}, ...`
    - `removed code_blocks: {id1}, {id2}, ...`
    - `updated code_blocks: {id1}, {id2}, ...`
 5. layout clause (optional), Format: `layout changed`
 6. comments clause(s), subformats:
    - `added comments: {id1}, {id2}, ...`
    - `removed comments: {id1}, {id2}, ...`
    - `updated comments: {id1}, {id2}, ...`
 7. todo_list clause(s) (only emitted if prev_todo != curr_todo), subformats:
    - `added todo_list` (if prev_todo is None and curr_todo is not None)
    - `removed todo_list` (if prev_todo is not None and curr_todo is None)
    - `todo_list.title: {prev_title}->{curr_title}` (only if both exist and titles differ)
    - todo task subformats (only if both exist):
      - `added todo tasks: {task_id1}, {task_id2}, ...`
      - `removed todo tasks: {task_id1}, {task_id2}, ...`
      - `updated todo tasks: {task_id1}, {task_id2}, ...`
 8. origin clause (optional), Format: `origin changed`
 9. tabs clause(s) (optional; includes per-tab internal unit/connection clauses), subformats:
    - `added tabs: {tab_id1}, {tab_id2}, ...`
    - `removed tabs: {tab_id1}, {tab_id2}, ...`
    - `tab[{tab_id}] meta changed`
    - per-tab unit/connection subformats (each prefixed with `tab[{tab_id}] `):
      - `tab[{tab_id}] added {N} units: ...`
      - `tab[{tab_id}] removed {N} units: ...`
      - `tab[{tab_id}] updated units: ...`
      - `tab[{tab_id}] connected {N}: ...`
      - `tab[{tab_id}] disconnected {N}: ...`
 10. metadata clause (optional), Format: `metadata changed`

"""

from __future__ import annotations

import json
from typing import Any, Literal

from core.schemas.process_graph import ProcessGraph

DiffFormat = Literal["str", "array", "payload"]


def _as_dict(x: ProcessGraph | dict[str, Any] | None) -> dict[str, Any] | None:
    if x is None:
        return None
    if isinstance(x, ProcessGraph):
        return x.model_dump(by_alias=True)
    return dict(x)


def _json_dumps(x: Any) -> str:
    return json.dumps(x, sort_keys=True, default=str, separators=(",", ":"))


def _norm_obj(x: Any) -> Any:
    # Recursively normalize dict/list ordering for stable comparisons.
    if isinstance(x, dict):
        return {k: _norm_obj(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_norm_obj(v) for v in x]
    return x


def _unit_fingerprint(u: dict[str, Any]) -> str:
    # Include fields that matter for meaning/roundtrip.
    keys = [
        "id",
        "type",
        "controllable",
        "params",
        "name",
        "input_ports",
        "output_ports",
    ]
    obj = {k: u.get(k) for k in keys if k in u}
    # Preserve any extra keys deterministically too.
    extra = {k: v for k, v in u.items() if k not in obj}
    if extra:
        obj["__extra__"] = extra
    return _json_dumps(_norm_obj(obj))


def _unit_id(u: Any) -> str | None:
    if not isinstance(u, dict):
        return None
    uid = u.get("id")
    return None if uid is None else str(uid)


def _units_by_id(g: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for u in g.get("units") or []:
        uid = _unit_id(u)
        if uid is None:
            continue
        out[uid] = _unit_fingerprint(u)
    return out


def _conn_signature(c: dict[str, Any]) -> tuple[str, str, str, str, str | None]:
    # Support both alias keys: "from"/"to" and "from_id"/"to_id".
    fr = c.get("from", c.get("from_id"))
    to = c.get("to", c.get("to_id"))
    fp = c.get("from_port", "0")
    tp = c.get("to_port", "0")
    ct = c.get("connection_type", None)

    fr_s = "?" if fr is None else str(fr)
    to_s = "?" if to is None else str(to)
    fp_s = "?" if fp is None else str(fp)
    tp_s = "?" if tp is None else str(tp)
    return (fr_s, to_s, fp_s, tp_s, None if ct is None else str(ct))


def _conn_pretty(sig: tuple[str, str, str, str, str | None]) -> str:
    a, b, fp, tp, ct = sig
    ct_s = ct if ct is not None else "none"
    return f"{a}->{b}[{fp}->{tp}]({ct_s})"


def _conns_by_sig(g: dict[str, Any]) -> set[tuple[str, str, str, str, str | None]]:
    out: set[tuple[str, str, str, str, str | None]] = set()
    for c in g.get("connections") or []:
        if isinstance(c, dict):
            out.add(_conn_signature(c))
    return out


def _graph_diff_for_units_and_conns(
    prev_g: dict[str, Any], curr_g: dict[str, Any], prefix: str = ""
) -> list[str]:
    parts: list[str] = []

    prev_units = _units_by_id(prev_g)
    curr_units = _units_by_id(curr_g)

    prev_ids = set(prev_units.keys())
    curr_ids = set(curr_units.keys())

    added_units = curr_ids - prev_ids
    removed_units = prev_ids - curr_ids
    updated_units = {
        uid for uid in (curr_ids & prev_ids) if prev_units[uid] != curr_units[uid]
    }

    if added_units:
        id_to_type = {
            str(u.get("id")): str(u.get("type") or "?")
            for u in (curr_g.get("units") or [])
            if isinstance(u, dict) and u.get("id") is not None
        }
        parts.append(
            f"{prefix}added {len(added_units)} units: "
            + ", ".join(
                f"{uid} ({id_to_type.get(uid, '?')})" for uid in sorted(added_units)
            )
        )

    if removed_units:
        parts.append(
            f"{prefix}removed {len(removed_units)} units: "
            + ", ".join(sorted(removed_units))
        )

    if updated_units:
        parts.append(f"{prefix}updated units: " + ", ".join(sorted(updated_units)))

    prev_conns = _conns_by_sig(prev_g)
    curr_conns = _conns_by_sig(curr_g)

    added_conns = curr_conns - prev_conns
    removed_conns = prev_conns - curr_conns

    if added_conns:
        parts.append(
            f"{prefix}connected {len(added_conns)}: "
            + ", ".join(_conn_pretty(s) for s in sorted(added_conns))
        )

    if removed_conns:
        parts.append(
            f"{prefix}disconnected {len(removed_conns)}: "
            + ", ".join(_conn_pretty(s) for s in sorted(removed_conns))
        )

    return parts


def _fingerprint_collection(
    items: list[Any], key: str, stable_shape: list[str]
) -> dict[str, str]:
    out: dict[str, str] = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        if it.get(key) is None:
            continue
        # Keep only stable_shape + extras for determinism.
        obj = {k: it.get(k) for k in stable_shape if k in it}
        extra = {k: v for k, v in it.items() if k not in obj}
        if extra:
            obj["__extra__"] = extra
        out[str(it.get(key))] = _json_dumps(_norm_obj(obj))
    return out


def graph_diff(
    prev: ProcessGraph | dict[str, Any] | None,
    current: ProcessGraph | dict[str, Any] | None,
    format: DiffFormat = "str",
) -> str | list[str] | dict[str, Any]:
    prev_d = _as_dict(prev)
    curr_d = _as_dict(current)
    if prev_d is None or curr_d is None:
        if format == "payload":
            return {}
        return "" if format == "str" else []

    # --- structured payload we want ---
    payload: dict[str, Any] = {
        "environment_type_changed": False,
        "environments_changed": False,

        # top-level (non-tab) diffs
        "units_added": [],
        "units_removed": [],
        "units_updated": [],
        "connections_added": [],
        "connections_removed": [],

        "code_blocks_added": [],
        "code_blocks_removed": [],
        "code_blocks_updated": [],

        "layout_changed": False,

        "comments_added": [],
        "comments_removed": [],
        "comments_updated": [],

        "origin_changed": False,

        # todo lists
        "todo_lists_added": [],          # list[str] (todo list ids)
        "todo_lists_removed": [],       # list[str]
        "todo_lists_updated": [],       # list[{"id": str, "title_changed"?: {"from":..., "to":...}, "tasks_added"?: [...], "tasks_removed"?: [...], "tasks_updated"?: [...]}]

        # tabs
        "tabs_added": [],
        "tabs_removed": [],
        "tab_meta_changed": [],
        "tabs": {},

        "metadata_changed": False,
    }


    # --- string parts for backward compat ---
    parts: list[str] = []

    # environments
    if prev_d.get("environment_type") != curr_d.get("environment_type"):
        payload["environment_type_changed"] = True
        if format != "payload":
            parts.append(
                f"environment_type: {prev_d.get('environment_type')}->{curr_d.get('environment_type')}"
            )

    if prev_d.get("environments") != curr_d.get("environments"):
        payload["environments_changed"] = True
        if format != "payload":
            parts.append("environments changed")

    # top-level units/connections:
    # Instead of calling _graph_diff_for_units_and_conns (which emits strings),
    # re-use its underlying logic but store structured results.
    prev_units = _units_by_id(prev_d)
    curr_units = _units_by_id(curr_d)

    prev_ids = set(prev_units.keys())
    curr_ids = set(curr_units.keys())

    added_units = curr_ids - prev_ids
    removed_units = prev_ids - curr_ids
    updated_units = {
        uid for uid in (curr_ids & prev_ids) if prev_units[uid] != curr_units[uid]
    }

    if added_units or removed_units or updated_units:
        # need type lookup for added_units (mirrors original implementation)
        id_to_type = {
            str(u.get("id")): str(u.get("type") or "?")
            for u in (curr_d.get("units") or [])
            if isinstance(u, dict) and u.get("id") is not None
        }

        payload["units_added"] = [
            {"id": uid, "type": id_to_type.get(uid, "?")} for uid in sorted(added_units)
        ]
        payload["units_removed"] = sorted(removed_units)
        payload["units_updated"] = sorted(updated_units)

        if format != "payload":
            if added_units:
                parts.append(
                    "added {} units: ".format(len(added_units))
                    + ", ".join(
                        f"{uid} ({id_to_type.get(uid, '?')})"
                        for uid in sorted(added_units)
                    )
                )
            if removed_units:
                parts.append(
                    "removed {} units: ".format(len(removed_units))
                    + ", ".join(sorted(removed_units))
                )
            if updated_units:
                parts.append("updated units: " + ", ".join(sorted(updated_units)))

    prev_conns = _conns_by_sig(prev_d)
    curr_conns = _conns_by_sig(curr_d)

    added_conns = curr_conns - prev_conns
    removed_conns = prev_conns - curr_conns

    if added_conns or removed_conns:
        # convert sig->structured. _conn_signature uses from,to,ports,connection_type.
        def sig_to_struct(sig: tuple[str, str, str, str, str | None]) -> dict[str, Any]:
            fr, to, fp, tp, ct = sig
            return {
                "from": fr,
                "to": to,
                "from_port": fp,
                "to_port": tp,
                "connection_type": ct,
            }

        payload["connections_added"] = [sig_to_struct(s) for s in sorted(added_conns)]
        payload["connections_removed"] = [
            sig_to_struct(s) for s in sorted(removed_conns)
        ]

        if format != "payload":
            if added_conns:
                parts.append(
                    f"connected {len(added_conns)}: "
                    + ", ".join(_conn_pretty(s) for s in sorted(added_conns))
                )
            if removed_conns:
                parts.append(
                    f"disconnected {len(removed_conns)}: "
                    + ", ".join(_conn_pretty(s) for s in sorted(removed_conns))
                )

    # code_blocks
    prev_code = prev_d.get("code_blocks") or []
    curr_code = curr_d.get("code_blocks") or []

    prev_code_fp = _fingerprint_collection(
        prev_code, "id", ["id", "language", "source"]
    )
    curr_code_fp = _fingerprint_collection(
        curr_code, "id", ["id", "language", "source"]
    )

    prev_code_ids = set(prev_code_fp)
    curr_code_ids = set(curr_code_fp)

    code_added = curr_code_ids - prev_code_ids
    code_removed = prev_code_ids - curr_code_ids
    code_updated = {
        cid
        for cid in (curr_code_ids & prev_code_ids)
        if prev_code_fp[cid] != curr_code_fp[cid]
    }

    payload["code_blocks_added"] = sorted(code_added)
    payload["code_blocks_removed"] = sorted(code_removed)
    payload["code_blocks_updated"] = sorted(code_updated)

    if format != "payload":
        if code_added:
            parts.append("added code_blocks: " + ", ".join(sorted(code_added)))
        if code_removed:
            parts.append("removed code_blocks: " + ", ".join(sorted(code_removed)))
        if code_updated:
            parts.append("updated code_blocks: " + ", ".join(sorted(code_updated)))

    # layout
    if _json_dumps(prev_d.get("layout") or None) != _json_dumps(
        curr_d.get("layout") or None
    ):
        payload["layout_changed"] = True
        if format != "payload":
            parts.append("layout changed")

    # comments
    prev_comments = prev_d.get("comments") or []
    curr_comments = curr_d.get("comments") or []

    prev_com_fp = _fingerprint_collection(
        prev_comments, "id", ["id", "info", "commenter", "created_at", "x", "y"]
    )
    curr_com_fp = _fingerprint_collection(
        curr_comments, "id", ["id", "info", "commenter", "created_at", "x", "y"]
    )

    prev_com_ids = set(prev_com_fp)
    curr_com_ids = set(curr_com_fp)

    com_added = curr_com_ids - prev_com_ids
    com_removed = prev_com_ids - curr_com_ids
    com_updated = {
        cid
        for cid in (curr_com_ids & prev_com_ids)
        if prev_com_fp[cid] != curr_com_fp[cid]
    }

    payload["comments_added"] = sorted(com_added)
    payload["comments_removed"] = sorted(com_removed)
    payload["comments_updated"] = sorted(com_updated)

    if format != "payload":
        if com_added:
            parts.append("added comments: " + ", ".join(sorted(com_added)))
        if com_removed:
            parts.append("removed comments: " + ", ".join(sorted(com_removed)))
        if com_updated:
            parts.append("updated comments: " + ", ".join(sorted(com_updated)))

    # todo_lists (new shape)
    prev_todos = prev_d.get("todo_lists") or []
    curr_todos = curr_d.get("todo_lists") or []

    def _by_id(lst):
        return {x.get("id"): x for x in (lst or []) if x is not None and x.get("id") is not None}

    prev_map = _by_id(prev_todos)
    curr_map = _by_id(curr_todos)

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    # lists added/removed
    if prev_ids != curr_ids or prev_todos != curr_todos:
        payload["todo_lists_added"] = sorted(curr_ids - prev_ids)
        payload["todo_lists_removed"] = sorted(prev_ids - curr_ids)

    # lists title changed + tasks diff per list id
    payload["todo_lists_updated"] = []  # list of dicts
    for tl_id in sorted(curr_ids & prev_ids):
        prev_tl = prev_map[tl_id] or {}
        curr_tl = curr_map[tl_id] or {}

        prev_title = prev_tl.get("title")
        curr_title = curr_tl.get("title")
        tl_changed = prev_title != curr_title

        prev_tasks = prev_tl.get("tasks") or []
        curr_tasks = curr_tl.get("tasks") or []

        # task fingerprint (keep exactly the fields you had)
        prev_task_fp = _fingerprint_collection(
            prev_tasks,
            "id",
            ["id", "text", "completed", "created_at", "implementer", "curator", "finished_at", "deadline"],
        )
        curr_task_fp = _fingerprint_collection(
            curr_tasks,
            "id",
            ["id", "text", "completed", "created_at", "implementer", "curator", "finished_at", "deadline"],
        )

        prev_task_ids = set(prev_task_fp.keys())
        curr_task_ids = set(curr_task_fp.keys())

        tasks_added = sorted(curr_task_ids - prev_task_ids)
        tasks_removed = sorted(prev_task_ids - curr_task_ids)
        tasks_updated = sorted(
            {
                tid
                for tid in (curr_task_ids & prev_task_ids)
                if prev_task_fp[tid] != curr_task_fp[tid]
            }
        )

        if tl_changed or tasks_added or tasks_removed or tasks_updated:
            entry = {"id": tl_id}
            if tl_changed:
                entry["title_changed"] = {"from": prev_title, "to": curr_title}

            if tasks_added:
                entry["tasks_added"] = tasks_added
            if tasks_removed:
                entry["tasks_removed"] = tasks_removed
            if tasks_updated:
                entry["tasks_updated"] = tasks_updated

            payload["todo_lists_updated"].append(entry)

    # optional: human-readable parts (only if format != "payload")
    if format != "payload":
        if payload.get("todo_lists_added"):
            parts.append("added todo lists: " + ", ".join(payload["todo_lists_added"]))
        if payload.get("todo_lists_removed"):
            parts.append(
                "removed todo lists: " + ", ".join(payload["todo_lists_removed"])
            )
        for u in payload.get("todo_lists_updated") or []:
            tl_id = u["id"]
            if "title_changed" in u:
                tc = u["title_changed"]
                parts.append(f"todo_list[{tl_id}].title: {tc['from']}->{tc['to']}")
            if u.get("tasks_added"):
                parts.append(
                    f"added todo tasks ({tl_id}): " + ", ".join(u["tasks_added"])
                )
            if u.get("tasks_removed"):
                parts.append(
                    f"removed todo tasks ({tl_id}): " + ", ".join(u["tasks_removed"])
                )
            if u.get("tasks_updated"):
                parts.append(
                    f"updated todo tasks ({tl_id}): " + ", ".join(u["tasks_updated"])
                )


    # origin
    if _json_dumps(prev_d.get("origin") or None) != _json_dumps(
        curr_d.get("origin") or None
    ):
        payload["origin_changed"] = True
        if format != "payload":
            parts.append("origin changed")

    # tabs
    prev_tabs = prev_d.get("tabs")
    curr_tabs = curr_d.get("tabs")
    if prev_tabs != curr_tabs:
        prev_tabs_list = prev_tabs or []
        curr_tabs_list = curr_tabs or []

        prev_tab_by_id = {
            str(t.get("id")): t
            for t in prev_tabs_list
            if isinstance(t, dict) and t.get("id") is not None
        }
        curr_tab_by_id = {
            str(t.get("id")): t
            for t in curr_tabs_list
            if isinstance(t, dict) and t.get("id") is not None
        }

        prev_tab_ids = set(prev_tab_by_id)
        curr_tab_ids = set(curr_tab_by_id)

        payload["tabs_added"] = sorted(curr_tab_ids - prev_tab_ids)
        payload["tabs_removed"] = sorted(prev_tab_ids - curr_tab_ids)

        if format != "payload":
            if payload["tabs_added"]:
                parts.append("added tabs: " + ", ".join(payload["tabs_added"]))
            if payload["tabs_removed"]:
                parts.append("removed tabs: " + ", ".join(payload["tabs_removed"]))

        for tid in sorted(curr_tab_ids & prev_tab_ids):
            pt = prev_tab_by_id[tid]
            ct = curr_tab_by_id[tid]

            if {"label": pt.get("label"), "disabled": pt.get("disabled")} != {
                "label": ct.get("label"),
                "disabled": ct.get("disabled"),
            }:
                payload["tab_meta_changed"].append(tid)
                if format != "payload":
                    parts.append(f"tab[{tid}] meta changed")

            # For simplicity you can skip per-tab structured unit/conn diffs
            # unless your merge step needs them. If needed, mirror the same
            # units/conns logic used for top-level but store under payload["tabs"][tid].
            if format != "payload":
                parts.extend(
                    _graph_diff_for_units_and_conns(
                        prev_g={
                            "units": pt.get("units") or [],
                            "connections": pt.get("connections") or [],
                        },
                        curr_g={
                            "units": ct.get("units") or [],
                            "connections": ct.get("connections") or [],
                        },
                        prefix=f"tab[{tid}] ",
                    )
                )

    # metadata
    if _json_dumps(prev_d.get("metadata") or None) != _json_dumps(
        curr_d.get("metadata") or None
    ):
        payload["metadata_changed"] = True
        if format != "payload":
            parts.append("metadata changed")

    # return
    if format == "payload":
        return payload
    if format == "array":
        return parts
    return "; ".join(parts) if parts else ""
