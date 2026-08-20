from __future__ import annotations

import logging
from typing import Any

from agents.chat.context.todo_list_manager.helpers import get_incomplete_tasks
from agents.chat.graph_bridge import get_live_graph_dict
from services.logging import setup_colored_logging
from units.registry import UnitSpec, register_unit

CHECK_TODO_INPUT_PORTS = [
    ("check_todo", "Any"),
    ("graph", "Any"),
]

CHECK_TODO_OUTPUT_PORTS = [
    ("tasks_todo", "Any"),
    ("error", "Any"),
]

logger = setup_colored_logging(logging.DEBUG)

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
            logger.debug("CheckTodo using live graph")

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

        graph: dict[str, Any] = {
            str(key): value for key, value in graph_dict.items()
        }

        incomplete_tasks = get_incomplete_tasks(
            current=graph,
            task_matches=None,
        )

        logger.info(
            "CheckTodo found %d incomplete task(s)",
            len(incomplete_tasks or []),
        )

        return (
            {
                "tasks_todo": list(incomplete_tasks or []),
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
                "Checks an optional input graph, or the live workflow graph, "
                "for incomplete todo tasks."
            ),
        )
    )


__all__ = ["CHECK_TODO_INPUT_PORTS", "CHECK_TODO_OUTPUT_PORTS", "register_check_todo"]
