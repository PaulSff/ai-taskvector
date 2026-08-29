"""
graph_diff(prev, current, format="str") supports three output formats:

- format="str" (default) returns a semicolon-separated string.
- format="array" returns list[str].
- format="payload" returns a structured dictionary describing all detected changes.

If prev is None or current is None:

- format="str" returns "".
- format="array" returns [].
- format="payload" returns {}.

For string and array formats, the function builds an ordered list of clause strings. A clause is included only when the corresponding difference is detected. The output order is:

1. Environment settings

   - `environment_type: {prev_value}->{curr_value}`
   - `environments changed`
   - `keep_alive: {prev_value}->{curr_value}`

2. Top-level units and connections

   - `added {N} units: {id1} ({type1}), {id2} ({type2}), ...`
   - `removed {N} units: {id1}, {id2}, ...`
   - `updated units: {id1}, {id2}, ...`
   - `connected {N}: {sig1}, {sig2}, ...`
   - `disconnected {N}: {sig1}, {sig2}, ...`

   Connection signatures use the format:

   `{source}->{target}[{source_port}->{target_port}]({connection_type})`

   A missing connection type is rendered as `none`.

3. Code blocks

   - `added code_blocks: {id1}, {id2}, ...`
   - `removed code_blocks: {id1}, {id2}, ...`
   - `updated code_blocks: {id1}, {id2}, ...`

4. Layout

   - `layout changed`

5. Comments

   - `added comments: {id1}, {id2}, ...`
   - `removed comments: {id1}, {id2}, ...`
   - `updated comments: {id1}, {id2}, ...`

6. Todo lists

   Todo-list clauses are emitted when applicable:

   - `added todo lists: {id1}, {id2}, ...`
   - `removed todo lists: {id1}, {id2}, ...`
   - `todo_list[{todo_id}].title: {prev_title}->{curr_title}`
   - `todo_list[{todo_id}].coordinates: ({prev_x},{prev_y})->({curr_x},{curr_y})`
   - `added todo tasks ({todo_id}): {task_id1}, {task_id2}, ...`
   - `removed todo tasks ({todo_id}): {task_id1}, {task_id2}, ...`
   - `updated todo tasks ({todo_id}): {task_id1}, {task_id2}, ...`

   Todo-list changes are compared by todo-list ID. Existing todo lists are inspected for title, coordinates, and task changes.

7. Tabs

   Tab clauses are emitted only when `previous.tabs != current.tabs`:

   - `added tabs: {tab_id1}, {tab_id2}, ...`
   - `removed tabs: {tab_id1}, {tab_id2}, ...`
   - `tab[{tab_id}] meta changed`

   Tab metadata changes include changes to `label` or `disabled`.

   Units and connections within an existing tab are reported using the same formats as top-level graph changes, prefixed with `tab[{tab_id}] `:

   - `tab[{tab_id}] added {N} units: ...`
   - `tab[{tab_id}] removed {N} units: ...`
   - `tab[{tab_id}] updated units: ...`
   - `tab[{tab_id}] connected {N}: ...`
   - `tab[{tab_id}] disconnected {N}: ...`

8. Origin

   - `origin changed`

9. Metadata

   - `metadata changed`

The `payload` format returns a dictionary with these keys:

- `environment_type_changed`: bool
- `environments_changed`: bool
- `keep_alive_changed`: bool
- `units_added`: list of objects containing `id` and `type`
- `units_removed`: list[str]
- `units_updated`: list[str]
- `connections_added`: list of objects containing `from`, `to`, `from_port`, `to_port`, and `connection_type`
- `connections_removed`: list of objects containing `from`, `to`, `from_port`, `to_port`, and `connection_type`
- `code_blocks_added`: list[str]
- `code_blocks_removed`: list[str]
- `code_blocks_updated`: list[str]
- `layout_changed`: bool
- `comments_added`: list[str]
- `comments_removed`: list[str]
- `comments_updated`: list[str]
- `origin_changed`: bool
- `todo_lists_added`: list[str]
- `todo_lists_removed`: list[str]
- `todo_lists_updated`: list of objects describing title, coordinate, and task changes for each affected existing todo list
- `tabs_added`: list[str]
- `tabs_removed`: list[str]
- `tab_meta_changed`: list[str]
- `tabs`: dict
- `metadata_changed`: bool

All collection IDs and change lists are sorted lexicographically. Unit and connection differences are determined by ID and connection signature, respectively. Updates are reported when matching objects differ by equality comparison.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal, Protocol, cast

from core.schemas.process_graph import (
    Connection,
    ProcessGraph,
)

DiffFormat = Literal["str", "array", "payload"]

class _HasId(Protocol):
    id: str


def _collection_by_id[T: _HasId](
    items: Iterable[T] | None,
) -> dict[str, T]:
    return {
        item.id: item
        for item in items or []
    }

def _changed_ids[T: _HasId](
    previous: Mapping[str, T],
    current: Mapping[str, T],
) -> tuple[list[str], list[str], list[str]]:
    previous_ids = set(previous)
    current_ids = set(current)

    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)
    updated = sorted(
        item_id
        for item_id in previous_ids & current_ids
        if previous[item_id] != current[item_id]
    )

    return added, removed, updated


ConnectionSignature = tuple[str, str, str, str, str | None]

def _connection_signature(
    connection: Connection,
) -> ConnectionSignature:
    return (
        connection.from_id,
        connection.to_id,
        connection.from_port,
        connection.to_port,
        connection.connection_type,
    )

def _connection_text(signature: ConnectionSignature) -> str:
    source, target, source_port, target_port, connection_type = signature

    return (
        f"{source}->{target}"
        f"[{source_port}->{target_port}]"
        f"({connection_type if connection_type is not None else 'none'})"
    )

def _connection_set(
    graph: ProcessGraph,
) -> set[ConnectionSignature]:
    return {
        _connection_signature(connection)
        for connection in graph.connections
    }

def _graph_parts(
    previous: ProcessGraph,
    current: ProcessGraph,
    prefix: str = "",
) -> list[str]:
    parts: list[str] = []

    previous_units = _collection_by_id(previous.units)
    current_units = _collection_by_id(current.units)

    added, removed, updated = _changed_ids(previous_units, current_units)

    if added:
        parts.append(
            f"{prefix}added {len(added)} units: "
            + ", ".join(
                f"{unit_id} ({current_units[unit_id].type})"
                for unit_id in added
            )
        )

    if removed:
        parts.append(
            f"{prefix}removed {len(removed)} units: "
            + ", ".join(removed)
        )

    if updated:
        parts.append(
            f"{prefix}updated units: " + ", ".join(updated)
        )

    previous_connections = _connection_set(previous)
    current_connections = _connection_set(current)

    added_connections = sorted(current_connections - previous_connections)
    removed_connections = sorted(previous_connections - current_connections)

    if added_connections:
        parts.append(
            f"{prefix}connected {len(added_connections)}: "
            + ", ".join(map(_connection_text, added_connections))
        )

    if removed_connections:
        parts.append(
            f"{prefix}disconnected {len(removed_connections)}: "
            + ", ".join(map(_connection_text, removed_connections))
        )

    return parts


def _diff_collection[T: _HasId](
    previous: Iterable[T] | None,
    current: Iterable[T] | None,
) -> tuple[list[str], list[str], list[str]]:
    return _changed_ids(
        _collection_by_id(previous),
        _collection_by_id(current),
    )


def _diff_todo_lists(
    prev: ProcessGraph,
    current: ProcessGraph,
    payload: dict[str, object],
    parts: list[str],
) -> None:
    previous = {
        todo.id: todo
        for todo in prev.todo_lists
    }
    current_lists = {
        todo.id: todo
        for todo in current.todo_lists
    }

    previous_ids = set(previous)
    current_ids = set(current_lists)

    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)

    payload["todo_lists_added"] = added
    payload["todo_lists_removed"] = removed

    if added:
        parts.append("added todo lists: " + ", ".join(added))

    if removed:
        parts.append("removed todo lists: " + ", ".join(removed))

    updated_lists_value = payload["todo_lists_updated"]

    if not isinstance(updated_lists_value, list):
        raise TypeError("payload['todo_lists_updated'] must be a list")

    updated_lists = cast(list[object], updated_lists_value)


    for todo_id in sorted(previous_ids & current_ids):
        old = previous[todo_id]
        new = current_lists[todo_id]

        entry: dict[str, object] = {"id": todo_id}

        if old.title != new.title:
            entry["title_changed"] = {
                "from": old.title,
                "to": new.title,
            }

            parts.append(
                f"todo_list[{todo_id}].title: "
                + f"{old.title}->{new.title}"
            )

        if old.x != new.x or old.y != new.y:
            entry["coordinates_changed"] = {
                "from": {
                    "x": old.x,
                    "y": old.y,
                },
                "to": {
                    "x": new.x,
                    "y": new.y,
                },
            }

            parts.append(
                f"todo_list[{todo_id}].coordinates: "
                + f"({old.x},{old.y})->({new.x},{new.y})"
            )

        old_tasks = {
            task.id: task
            for task in old.tasks
        }
        new_tasks = {
            task.id: task
            for task in new.tasks
        }

        task_added, task_removed, task_updated = _changed_ids(
            old_tasks,
            new_tasks,
        )

        if task_added:
            entry["tasks_added"] = task_added
            parts.append(
                f"added todo tasks ({todo_id}): "
                + ", ".join(task_added)
            )

        if task_removed:
            entry["tasks_removed"] = task_removed
            parts.append(
                f"removed todo tasks ({todo_id}): "
                + ", ".join(task_removed)
            )

        if task_updated:
            entry["tasks_updated"] = task_updated
            parts.append(
                f"updated todo tasks ({todo_id}): "
                + ", ".join(task_updated)
            )

        if len(entry) > 1:
            updated_lists.append(entry)


def _diff_tabs(
    previous: ProcessGraph,
    current: ProcessGraph,
    payload: dict[str,object],
    parts: list[str],
) -> None:
    if previous.tabs == current.tabs:
        return

    previous_tabs = {
        tab.id: tab
        for tab in previous.tabs or []
    }
    current_tabs = {
        tab.id: tab
        for tab in current.tabs or []
    }

    previous_ids = set(previous_tabs)
    current_ids = set(current_tabs)

    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)

    payload["tabs_added"] = added
    payload["tabs_removed"] = removed

    if added:
        parts.append("added tabs: " + ", ".join(added))

    if removed:
        parts.append("removed tabs: " + ", ".join(removed))

    meta_changed: list[str] = []

    for tab_id in sorted(previous_ids & current_ids):
        old_tab = previous_tabs[tab_id]
        new_tab = current_tabs[tab_id]

        if (
            old_tab.label != new_tab.label
            or old_tab.disabled != new_tab.disabled
        ):
            meta_changed.append(tab_id)
            parts.append(f"tab[{tab_id}] meta changed")

        old_graph = ProcessGraph(
            units=old_tab.units,
            connections=old_tab.connections,
        )
        new_graph = ProcessGraph(
            units=new_tab.units,
            connections=new_tab.connections,
        )

        parts.extend(
            _graph_parts(
                old_graph,
                new_graph,
                prefix=f"tab[{tab_id}] ",
            )
        )

    payload["tab_meta_changed"] = meta_changed

# Main entry-point for the graph diff
def graph_diff(
    prev: ProcessGraph | None,
    current: ProcessGraph | None,
    format: DiffFormat = "str",
) -> str | list[str] | dict[str, object]:
    if prev is None or current is None:
        if format == "payload":
            return {}

        return [] if format == "array" else ""

    environment_type_changed = (
        prev.environment_type != current.environment_type
    )
    environments_changed = prev.environments != current.environments
    keep_alive_changed = prev.keep_alive != current.keep_alive
    layout_changed = prev.layout != current.layout
    origin_changed = prev.origin != current.origin
    metadata_changed = prev.metadata != current.metadata

    payload: dict[str, object] = {
        "environment_type_changed": environment_type_changed,
        "environments_changed": environments_changed,
        "keep_alive_changed": keep_alive_changed,

        "units_added": [],
        "units_removed": [],
        "units_updated": [],
        "connections_added": [],
        "connections_removed": [],

        "code_blocks_added": [],
        "code_blocks_removed": [],
        "code_blocks_updated": [],

        "layout_changed": layout_changed,

        "comments_added": [],
        "comments_removed": [],
        "comments_updated": [],

        "origin_changed": origin_changed,

        "todo_lists_added": [],
        "todo_lists_removed": [],
        "todo_lists_updated": [],

        "tabs_added": [],
        "tabs_removed": [],
        "tab_meta_changed": [],
        "tabs": {},

        "metadata_changed": metadata_changed,
    }

    parts: list[str] = []

    if environment_type_changed:
        parts.append(
            "environment_type: "
            + f"{prev.environment_type.value}->{current.environment_type.value}"
        )

    if environments_changed:
        parts.append("environments changed")

    if keep_alive_changed:
        parts.append(
            f"keep_alive: {prev.keep_alive}->{current.keep_alive}"
        )

    previous_units = _collection_by_id(prev.units)
    current_units = _collection_by_id(current.units)

    units_added, units_removed, units_updated = _changed_ids(
        previous_units,
        current_units,
    )

    payload["units_added"] = [
        {
            "id": unit_id,
            "type": current_units[unit_id].type,
        }
        for unit_id in units_added
    ]
    payload["units_removed"] = units_removed
    payload["units_updated"] = units_updated

    parts.extend(_graph_parts(prev, current))

    previous_connections = _connection_set(prev)
    current_connections = _connection_set(current)

    added_connections = sorted(
        current_connections - previous_connections
    )
    removed_connections = sorted(
        previous_connections - current_connections
    )

    payload["connections_added"] = [
        {
            "from": source,
            "to": target,
            "from_port": source_port,
            "to_port": target_port,
            "connection_type": connection_type,
        }
        for source, target, source_port, target_port, connection_type
        in added_connections
    ]

    payload["connections_removed"] = [
        {
            "from": source,
            "to": target,
            "from_port": source_port,
            "to_port": target_port,
            "connection_type": connection_type,
        }
        for source, target, source_port, target_port, connection_type
        in removed_connections
    ]

    code_added, code_removed, code_updated = _diff_collection(
        prev.code_blocks,
        current.code_blocks,
    )

    payload["code_blocks_added"] = code_added
    payload["code_blocks_removed"] = code_removed
    payload["code_blocks_updated"] = code_updated

    if code_added:
        parts.append(
            "added code_blocks: " + ", ".join(code_added)
        )

    if code_removed:
        parts.append(
            "removed code_blocks: " + ", ".join(code_removed)
        )

    if code_updated:
        parts.append(
            "updated code_blocks: " + ", ".join(code_updated)
        )

    if layout_changed:
        parts.append("layout changed")

    comments_added, comments_removed, comments_updated = _diff_collection(
        prev.comments,
        current.comments,
    )

    payload["comments_added"] = comments_added
    payload["comments_removed"] = comments_removed
    payload["comments_updated"] = comments_updated

    if comments_added:
        parts.append(
            "added comments: " + ", ".join(comments_added)
        )

    if comments_removed:
        parts.append(
            "removed comments: " + ", ".join(comments_removed)
        )

    if comments_updated:
        parts.append(
            "updated comments: " + ", ".join(comments_updated)
        )

    _diff_todo_lists(prev, current, payload, parts)
    _diff_tabs(prev, current, payload, parts)

    if origin_changed:
        parts.append("origin changed")

    if metadata_changed:
        parts.append("metadata changed")

    if format == "payload":
        return payload

    if format == "array":
        return parts

    return "; ".join(parts)
