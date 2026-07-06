from __future__ import annotations

import logging
from typing import Any, Literal, get_args

from core.graph.batch_edits import apply_workflow_edits
from core.graph.graph_edits import GraphEditAction
from core.schemas import ProcessGraph

logger = logging.getLogger(__name__)

DiffFormat = Literal["str", "array", "payload"]


# ---------- helpers ----------


def _to_plain_dict(x: Any) -> dict[str, Any]:
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    md = getattr(x, "model_dump", None)
    if callable(md):
        dumped = md(by_alias=True)
        return dumped if isinstance(dumped, dict) else {}
    try:
        d = dict(x)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _to_unit_payload(u: Any) -> dict[str, Any] | None:
    if not isinstance(u, dict):
        return None
    uid = u.get("id")
    if uid is None:
        return None
    return {
        "id": str(uid),
        "type": str(u.get("type") or "?"),
        "controllable": bool(u.get("controllable", True)),
        "params": u.get("params") or {},
        "name": u.get("name"),
    }


def _to_conn_payload(c: Any) -> dict[str, Any] | None:
    if not isinstance(c, dict):
        return None
    fr = c.get("from", c.get("from_id"))
    to = c.get("to", c.get("to_id"))
    if fr is None or to is None:
        return None
    return {
        "from": str(fr),
        "to": str(to),
        "from_port": str(c.get("from_port", "0")),
        "to_port": str(c.get("to_port", "0")),
    }


def _apply_edits_safe(
    prev_d: dict[str, Any], actions: list[dict[str, Any]]
) -> dict[str, Any]:
    try:
        return apply_workflow_edits(
            prev_d,
            actions,
            allowed_actions=frozenset(get_args(GraphEditAction)),
        )
    except Exception as e:
        logger.error("apply_workflow_edits failed: %s", e, exc_info=True)
        return {"success": False, "graph": prev_d, "error": str(e)}


# ---------- merger ----------


def merge_graph_actions_from_diff(
    prev: ProcessGraph | dict[str, Any] | None,
    current: ProcessGraph | dict[str, Any] | None,
    graph_diff_fn,
) -> dict[str, Any]:
    # structured diff payload
    try:
        payload = graph_diff_fn(prev, current, format="payload")
    except Exception as e:
        logger.error("graph_diff_fn failed: %s", e, exc_info=True)
        prev_d = _to_plain_dict(prev)
        return {
            "Multiple_edits_sequential": [],
            "success": False,
            "graph": prev_d,
            "error": str(e),
        }

    # normalize prev/current to dict once
    prev_d = _to_plain_dict(prev)
    curr_d = _to_plain_dict(current)

    # ensure payload is a dict (graph_diff_fn may return {} in "no prev/curr" case)
    if not isinstance(payload, dict):
        payload = {}

    # Gather structured changes (only the fields we need for merge)
    units_added = payload.get("units_added") or []
    units_removed = payload.get("units_removed") or []
    units_updated = payload.get("units_updated") or []

    connections_added = payload.get("connections_added") or []

    # todo/comments are represented by ids in the payload
    add_todo_list = bool(payload.get("todo_list_added"))
    remove_todo_list = bool(payload.get("todo_list_removed"))

    add_tasks = payload.get("todo_tasks_added") or []
    remove_tasks = payload.get("todo_tasks_removed") or []

    added_comments = payload.get("comments_added") or []

    # replace if both have unit ids, disjoint, and there are no updated_units.
    prev_unit_ids = {
        str(u.get("id"))
        for u in (prev_d.get("units") or [])
        if isinstance(u, dict) and u.get("id") is not None
    }
    curr_unit_ids = {
        str(u.get("id"))
        for u in (curr_d.get("units") or [])
        if isinstance(u, dict) and u.get("id") is not None
    }

    replace_graph_needed = (
        bool(prev_unit_ids or curr_unit_ids)
        and prev_unit_ids.isdisjoint(curr_unit_ids)
        and not (units_updated or [])
    )

    actions: list[dict[str, Any]] = []

    # 0. replace_graph
    if replace_graph_needed:
        units: list[dict[str, Any]] = []
        for u in curr_d.get("units") or []:
            u_payload = _to_unit_payload(u)
            if u_payload is not None:
                units.append(u_payload)

        conns: list[dict[str, Any]] = []
        for c in curr_d.get("connections") or []:
            c_payload = _to_conn_payload(c)
            if c_payload is not None:
                conns.append(c_payload)

        actions = [{"action": "replace_graph", "units": units, "connections": conns}]
        res = _apply_edits_safe(prev_d, actions)
        return {
            "Multiple_edits_sequential": actions,
            "success": res.get("success", False),
            "graph": res.get("graph", prev_d),
            "error": res.get("error"),
        }

    # 1. Add units
    for u in units_added:
        if not isinstance(u, dict):
            continue
        uid = u.get("id")
        utype = u.get("type")
        if uid is None:
            continue
        actions.append(
            {
                "action": "add_unit",
                "unit": {
                    "id": str(uid),
                    "type": str(utype or "?"),
                    "controllable": True,
                    "params": {},
                },
            }
        )

    # 2. Add connections (with ports)
    for c in connections_added:
        if not isinstance(c, dict):
            continue
        fr = c.get("from")
        to = c.get("to")
        fp = c.get("from_port", "0")
        tp = c.get("to_port", "0")
        if fr is None or to is None:
            continue
        actions.append(
            {
                "action": "connect",
                "from": str(fr),
                "to": str(to),
                "from_port": str(fp),
                "to_port": str(tp),
            }
        )

    # 3. Remove units
    for uid in units_removed:
        actions.append({"action": "remove_unit", "unit_id": str(uid)})

    # 4. Add todo lists
    if add_todo_list:
        actions.append({"action": "add_todo_list", "title": ""})

    # 5. Remove todo lists
    if remove_todo_list:
        actions.append({"action": "remove_todo_list"})

    # 6. Add tasks
    for tid in add_tasks:
        actions.append({"action": "add_task", "text": ""})

    # 7. Remove tasks
    for tid in remove_tasks:
        actions.append({"action": "remove_task", "task_id": str(tid)})

    # 8. Add comments
    for cid in added_comments:
        actions.append({"action": "add_comment", "info": ""})

    # 9. Apply the batch edits onto the graph
    res = _apply_edits_safe(prev_d, actions)

    return {
        "Multiple_edits_sequential": actions,
        "success": res.get("success", False),
        "graph": res.get("graph", prev_d),
        "error": res.get("error"),
    }
