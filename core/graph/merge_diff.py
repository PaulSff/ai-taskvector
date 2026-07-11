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


def _todo_lists_by_id(graph_d: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for tl in graph_d.get("todo_lists") or []:
        if isinstance(tl, dict) and tl.get("id") is not None:
            out[str(tl["id"])] = tl
    return out


def _tasks_by_id(todo_list: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for t in todo_list.get("tasks") or []:
        if isinstance(t, dict) and t.get("id") is not None:
            out[str(t["id"])] = t
    return out


def _append_todo_list_merge_actions(
    actions: list[dict[str, Any]],
    *,
    prev_d: dict[str, Any],
    curr_d: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    """Translate graph_diff todo_lists payload into apply_graph_edit actions."""
    curr_todos = _todo_lists_by_id(curr_d)
    prev_todos = _todo_lists_by_id(prev_d)
    multi_list = len(prev_todos) > 1 or len(curr_todos) > 1

    for list_id in payload.get("todo_lists_added") or []:
        tl = curr_todos.get(str(list_id)) or {}
        actions.append(
            {
                "action": "add_todo_list",
                "id": str(list_id),
                "title": tl.get("title"),
            }
        )

    for list_id in payload.get("todo_lists_removed") or []:
        actions.append({"action": "remove_todo_list", "id": str(list_id)})

    for entry in payload.get("todo_lists_updated") or []:
        if not isinstance(entry, dict):
            continue
        tl_id = entry.get("id")
        if tl_id is None:
            continue
        tl_id = str(tl_id)
        curr_tl = curr_todos.get(tl_id) or {}
        curr_tasks = _tasks_by_id(curr_tl)

        # FIX: apply todo list title changes
        if entry.get("title_changed") is not None:
            actions.append(
                {
                    "action": "set_todo_list_title",
                    "todo_list_id": tl_id,
                    "title": entry.get("title_changed"),
                }
            )

        for task_id in entry.get("tasks_added") or []:
            task = curr_tasks.get(str(task_id)) or {}
            text = task.get("text")
            if not text or not str(text).strip():
                continue

            act: dict[str, Any] = {
                "action": "add_task",
                "text": str(text).strip(),
                "task_id": str(task_id),
            }
            if multi_list:
                act["todo_list_id"] = tl_id

            # optional fields on add
            if "implementer" in task:
                act["implementer"] = task.get("implementer")
            if "deadline" in task:
                act["deadline"] = task.get("deadline")

            actions.append(act)

        for task_id in entry.get("tasks_removed") or []:
            act = {"action": "remove_task", "task_id": str(task_id)}
            if multi_list:
                act["todo_list_id"] = tl_id
            actions.append(act)

        for task_id in entry.get("tasks_updated") or []:
            task = curr_tasks.get(str(task_id)) or {}

            # completed -> mark_completed (also manages finished_at when completed=True)
            act_base = {
                "action": "mark_completed",
                "task_id": str(task_id),
                "completed": bool(task.get("completed", False)),
            }
            if multi_list:
                act_base["todo_list_id"] = tl_id
            actions.append(act_base)

            # optional fields
            if "implementer" in task:
                act = {
                    "action": "set_implementer",
                    "task_id": str(task_id),
                    "implementer": task.get("implementer"),
                }
                if multi_list:
                    act["todo_list_id"] = tl_id
                actions.append(act)

            if "curator" in task:
                act = {
                    "action": "set_curator",
                    "task_id": str(task_id),
                    "curator": task.get("curator"),
                }
                if multi_list:
                    act["todo_list_id"] = tl_id
                actions.append(act)

            if "deadline" in task:
                act = {
                    "action": "set_deadline",
                    "task_id": str(task_id),
                    "deadline": task.get("deadline"),
                }
                if multi_list:
                    act["todo_list_id"] = tl_id
                actions.append(act)



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

    added_comments = payload.get("comments_added") or []

    # replace only when both sides have units and ids are fully disjoint (never wipe
    # in-memory graph because on-disk import is empty / stale).
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
        bool(prev_unit_ids and curr_unit_ids)
        and prev_unit_ids.isdisjoint(curr_unit_ids)
        and not (units_updated or [])
    )

    # On-disk snapshot is empty/stale while in-memory graph still has units: keep memory.
    if prev_unit_ids and not curr_unit_ids:
        return {
            "Multiple_edits_sequential": [],
            "success": True,
            "graph": prev_d,
            "error": None,
        }

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

        graph_after = res.get("graph", prev_d)

        try:
            ProcessGraph.model_validate(graph_after)
        except Exception as e:
            logger.error("merged graph validation failed: %s", e, exc_info=True)
            return {
                "Multiple_edits_sequential": actions,
                "success": False,
                "graph": prev_d,
                "error": str(e),
            }

        return {
            "Multiple_edits_sequential": actions,
            "success": res.get("success", False),
            "graph": graph_after,
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

    # 4. Todo lists / tasks (todo_lists shape from graph_diff)
    _append_todo_list_merge_actions(
        actions, prev_d=prev_d, curr_d=curr_d, payload=payload
    )

    # 5. Add comments
    for cid in added_comments:
        actions.append({"action": "add_comment", "info": ""})

    # 6. Apply the batch edits onto the graph
    res = _apply_edits_safe(prev_d, actions)
    graph_after = res.get("graph", prev_d)

    # validate merged graph
    try:
        ProcessGraph.model_validate(graph_after)
    except Exception as e:
        logger.error("merged graph validation failed: %s", e, exc_info=True)
        return {
            "Multiple_edits_sequential": actions,
            "success": False,
            "graph": prev_d,
            "error": str(e),
        }

    return {
        "Multiple_edits_sequential": actions,
        "success": res.get("success", False),
        "graph": graph_after,
        "error": res.get("error"),
    }
