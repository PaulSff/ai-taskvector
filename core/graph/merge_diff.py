from __future__ import annotations

import logging
from typing import get_args

from core.graph.batch_edits import apply_workflow_edits
from core.schemas import ProcessGraph, TodoList, TodoTask
from core.schemas.graph_edit_api import (
    ApplyWorkflowEditsResult,
    GraphEdit,
    GraphEditAction,
    GraphEditUnit,
    MultipleEditsSequential,
)
from core.schemas.process_graph_diff import (
    GraphDiffFunction,
    GraphDiffPayload,
    MergeResult,
)

logger = logging.getLogger(__name__)

# ---------- helpers ----------

def _todo_lists_by_id(graph: ProcessGraph) -> dict[str, TodoList]:
    return {
        todo_list.id: todo_list
        for todo_list in graph.todo_lists
    }

def _tasks_by_id(todo_list: TodoList) -> dict[str, TodoTask]:
    return {
        task.id: task
        for task in todo_list.tasks
    }


def _append_todo_list_merge_actions(
    actions: list[GraphEdit],
    *,
    prev_graph: ProcessGraph,
    current_graph: ProcessGraph,
    payload: GraphDiffPayload,
) -> None:
    """Translate todo-list diff data into GraphEdit objects."""

    previous_todos = _todo_lists_by_id(prev_graph)
    current_todos = _todo_lists_by_id(current_graph)

    multi_list = len(previous_todos) > 1 or len(current_todos) > 1

    for list_id in payload["todo_lists_added"]:
        todo_list = current_todos.get(str(list_id))

        if todo_list is None:
            continue

        edit = GraphEdit(
            action="add_todo_list",
            id=todo_list.id,
        )

        if todo_list.title is not None:
            edit.title = todo_list.title

        actions.append(edit)

    for list_id in payload["todo_lists_removed"]:
        actions.append(
            GraphEdit(
                action="remove_todo_list",
                id=str(list_id),
            )
        )

    for entry in payload["todo_lists_updated"]:
        todo_list_id = entry["id"]
        todo_list = current_todos.get(todo_list_id)

        if todo_list is None:
            continue

        current_tasks = _tasks_by_id(todo_list)

        title_changed = entry.get("title_changed")

        if isinstance(title_changed, str):
            actions.append(
                GraphEdit(
                    action="set_todo_list_title",
                    todo_list_id=todo_list_id,
                    title=title_changed,
                )
            )

        tasks_added = entry.get("tasks_added")

        if isinstance(tasks_added, list):
            for task_id in tasks_added:
                task = current_tasks.get(str(task_id))

                if task is None or not task.text.strip():
                    continue

                edit = GraphEdit(
                    action="add_task",
                    text=task.text.strip(),
                    task_id=task.id,
                )

                if multi_list:
                    edit.todo_list_id = todo_list_id

                if task.implementer is not None:
                    edit.implementer = task.implementer

                if task.deadline is not None:
                    edit.deadline = task.deadline

                actions.append(edit)

        tasks_removed = entry.get("tasks_removed")

        if isinstance(tasks_removed, list):
            for task_id in tasks_removed:
                edit = GraphEdit(
                    action="remove_task",
                    task_id=str(task_id),
                )

                if multi_list:
                    edit.todo_list_id = todo_list_id

                actions.append(edit)

        tasks_updated = entry.get("tasks_updated")

        if isinstance(tasks_updated, list):
            for task_id in tasks_updated:
                task = current_tasks.get(str(task_id))

                if task is None:
                    continue

                edit = GraphEdit(
                    action="mark_completed",
                    task_id=task.id,
                    completed=task.completed,
                )

                if multi_list:
                    edit.todo_list_id = todo_list_id

                actions.append(edit)

                if task.implementer is not None:
                    edit = GraphEdit(
                        action="set_implementer",
                        task_id=task.id,
                        implementer=task.implementer,
                    )

                    if multi_list:
                        edit.todo_list_id = todo_list_id

                    actions.append(edit)

                if task.curator is not None:
                    edit = GraphEdit(
                        action="set_curator",
                        task_id=task.id,
                        curator=task.curator,
                    )

                    if multi_list:
                        edit.todo_list_id = todo_list_id

                    actions.append(edit)

                if task.deadline is not None:
                    edit = GraphEdit(
                        action="set_deadline",
                        task_id=task.id,
                        deadline=task.deadline,
                    )

                    if multi_list:
                        edit.todo_list_id = todo_list_id

                    actions.append(edit)


def _apply_edits_safe(
    prev_d: ProcessGraph,
    actions: MultipleEditsSequential,
) -> ApplyWorkflowEditsResult:
    try:
        return apply_workflow_edits(
            prev_d,
            actions,
            allowed_actions=frozenset(get_args(GraphEditAction)),
        )
    except (TypeError, ValueError) as e:
        logger.exception("apply_workflow_edits failed")

        return ApplyWorkflowEditsResult(
            success=False,
            graph=prev_d,
            error=str(e),
        )


# ---------- merger ----------

def merge_graph_actions_from_diff(
    prev: ProcessGraph | None,
    current: ProcessGraph | None,
    graph_diff_fn: GraphDiffFunction,
) -> MergeResult:
    try:
        diff_result = graph_diff_fn(
            prev,
            current,
            format="payload",
        )
    except (TypeError, ValueError) as e:
        logger.exception("graph_diff_fn failed")

        return MergeResult(
            multiple_edits_sequential=MultipleEditsSequential(),
            success=False,
            graph=prev or ProcessGraph(),
            error=str(e),
        )

    if not isinstance(diff_result, dict):
        raise TypeError(
            "graph_diff_fn(..., format='payload') must return GraphDiffPayload"
        )

    payload: GraphDiffPayload = diff_result
    prev_graph = prev or ProcessGraph()

    if current is None:
        return MergeResult(
            multiple_edits_sequential=MultipleEditsSequential(),
            success=True,
            graph=prev_graph,
            error=None,
        )

    prev_unit_ids = {str(unit.id) for unit in prev_graph.units}
    curr_unit_ids = {str(unit.id) for unit in current.units}

    replace_graph_needed = (
        bool(prev_unit_ids and curr_unit_ids)
        and prev_unit_ids.isdisjoint(curr_unit_ids)
        and not payload["units_updated"]
    )

    if prev_unit_ids and not curr_unit_ids:
        return MergeResult(
            multiple_edits_sequential=MultipleEditsSequential(),
            success=True,
            graph=prev_graph,
            error=None,
        )

    actions: list[GraphEdit] = []

    if replace_graph_needed:
        units = [
            unit.model_dump(exclude_none=True)
            for unit in current.units
        ]

        connections = [
            connection.model_dump(
                by_alias=True,
                exclude_none=True,
            )
            for connection in current.connections
        ]

        actions.append(
            GraphEdit(
                action="replace_graph",
                units=units,
                connections=connections,
            )
        )

    else:
        for unit in payload["units_added"]:
            actions.append(
                GraphEdit(
                    action="add_unit",
                    unit=GraphEditUnit(
                        id=unit["id"],
                        type=unit["type"],
                        controllable=True,
                        params={},
                    ),
                )
            )

        for connection in payload["connections_added"]:
            actions.append(
                GraphEdit.model_validate(
                    {
                        "action": "connect",
                        "from": str(connection["from"]),
                        "to": str(connection["to"]),
                        "from_port": str(connection["from_port"]),
                        "to_port": str(connection["to_port"]),
                    }
                )
            )

        for unit_id in payload["units_removed"]:
            actions.append(
                GraphEdit(
                    action="remove_unit",
                    unit_id=str(unit_id),
                )
            )

        _append_todo_list_merge_actions(
            actions,
            prev_graph=prev_graph,
            current_graph=current,
            payload=payload,
        )

        for _comment_id in payload["comments_added"]:
            actions.append(
                GraphEdit(
                    action="add_comment",
                    info="",
                )
            )

    edit_sequence = MultipleEditsSequential(
        edits=actions,
    )

    result = _apply_edits_safe(
        prev_graph,
        edit_sequence,
    )

    return MergeResult(
        multiple_edits_sequential=edit_sequence,
        success=result.success,
        graph=result.graph,
        error=result.error,
    )
