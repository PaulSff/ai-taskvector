"""
CheckTodo unit.

Checks a workflow graph for incomplete todo tasks.

Graph resolution order:

1. Use the graph provided through the optional ``graph`` input port.
2. If no input graph is provided, use the live graph from
   ``get_live_graph_dict()``.
3. If no live graph is available, import the latest saved workflow graph
   using ``import_latest_workflow_graph()``.

The required action input is:

    {
        "action": "check_todo"
    }

Example input using an explicitly supplied graph:

    inputs = {
        "check_todo": {
            "action": "check_todo"
        },
        "graph": {
            "units": [],
            "todo_lists": [
                {
                    "id": "todo-1",
                    "tasks": [
                        {
                            "id": "task-1",
                            "completed": False
                        }
                    ]
                }
            ]
        }
    }

If incomplete tasks are found, the unit returns:

    {
        "tasks_todo": {
            "type": "update",
            "update": {
                "tasks_todo": [
                    {
                        "todo_list_id": "todo-1",
                        "task": {
                            "id": "task-1",
                            "completed": False
                        }
                    }
                ]
            }
        },
        "error": None,
    }


If no incomplete tasks are found, the unit returns:

     {
         "tasks_todo": {
             "type": "update",
             "update": {
                 "tasks_todo": []
             }
         },
         "error": None,
     }

If the graph is unavailable or graph loading fails, the unit returns:

    {
        "tasks_todo": None,
        "error": {
            "error": "...",
            "message": "...",
        },
    }
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from agents.chat.context.todo_list_manager.helpers import get_incomplete_tasks
from agents.chat.graph_bridge import get_live_graph_dict
from agents.chat.utils.workflow_manager import import_latest_workflow_graph
from core.schemas import ProcessGraph
from units.registry import UnitSpec, register_unit

CHECK_TODO_INPUT_PORTS = [
    ("check_todo", "Any"),
    ("graph", "Any"),
]

CHECK_TODO_OUTPUT_PORTS = [
    ("tasks_todo", "Any"),
    ("error", "Any"),
]


logger = logging.getLogger("CheckTodo")


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if isinstance(value, dict):
        result: dict[str, Any] = {}

        for key, item in value.items():
            result[str(key)] = _to_jsonable(item)

        return result

    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]

    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]

    return value


def _check_todo_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    del params, dt

    action_input = inputs.get("check_todo")

    if not isinstance(action_input, dict):
        return (
            {
                "tasks_todo": None,
                "error": {
                    "error": "invalid_action",
                    "message": "check_todo must be an object.",
                },
            },
            state,
        )

    if action_input.get("action") != "check_todo":
        return (
            {
                "tasks_todo": None,
                "error": {
                    "error": "invalid_action",
                    "message": "Expected action 'check_todo'.",
                },
            },
            state,
        )

    try:
        graph_input = inputs.get("graph")

        if graph_input is not None:
            graph_dict = graph_input
            logger.debug("CheckTodo using graph from input port")

        else:
            graph_dict = get_live_graph_dict()

            if graph_dict is not None:
                logger.debug("CheckTodo using live graph")

            else:
                logger.debug(
                    "CheckTodo: No live graph available; importing latest workflow graph"
                )

                graph_result = import_latest_workflow_graph()

                if graph_result.error:
                    logger.error(
                        "Failed to import latest workflow graph: %s",
                        graph_result.error,
                    )

                    return (
                        {
                            "tasks_todo": None,
                            "error": {
                                "error": "graph_import_failed",
                                "message": str(graph_result.error),
                            },
                        },
                        state,
                    )

                graph_dict = graph_result.graph

                logger.debug(
                    "CheckTodo: Imported latest workflow graph from %s",
                    graph_result.picked_workflow_path,
                )

        if not isinstance(graph_dict, dict):
            return (
                {
                    "tasks_todo": None,
                    "error": {
                        "error": "graph_unavailable",
                        "message": "No valid workflow graph is available.",
                    },
                },
                state,
            )

        graph_data = {
            str(key): value for key, value in graph_dict.items()
        }

        try:
            graph = ProcessGraph.model_validate(graph_data)
        except ValidationError as exc:
            return (
                {
                    "tasks_todo": None,
                    "error": {
                        "error": "invalid_graph",
                        "message": str(exc),
                    },
                },
                state,
            )

        incomplete_tasks = get_incomplete_tasks(
            current=graph,
            task_matches=None,
        )

        # Serialize todo tasks to JSON-compatible values.
        incomplete_tasks_json = _to_jsonable(list(incomplete_tasks or []))

        tasks_todo = {
            "type": "update",
            "update": {
                "tasks_todo": incomplete_tasks_json,
            },
        }

        logger.info(
            "CheckTodo: found %d incomplete task(s)",
            len(incomplete_tasks_json),
        )

        return (
            {
                "tasks_todo": tasks_todo,
                "error": None,
            },
            state,
        )

    except Exception as exc:
        logger.exception("CheckTodo failed")

        return (
            {
                "tasks_todo": None,
                "error": {
                    "error": "check_todo_failed",
                    "message": str(exc),
                },
            },
            state,
        )


def register_check_todo() -> None:
    register_unit(
        UnitSpec(
            type_name="CheckTodo",
            input_ports=CHECK_TODO_INPUT_PORTS,
            output_ports=CHECK_TODO_OUTPUT_PORTS,
            step_fn=_check_todo_step,
            environment_tags=["taskvector"],
            environment_tags_are_agnostic=False,
            description=(
                "Checks an optional input graph, then the live graph, and "
                "finally the latest saved workflow graph for incomplete "
                "todo tasks."
            ),
        )
    )


__all__ = ["register_check_todo"]
