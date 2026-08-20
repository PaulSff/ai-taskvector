from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future
from typing import Any

from agents.chat.context_gateway import run_agentic_turn
from services.logging import setup_colored_logging
from units.registry import UnitSpec, register_unit

AGENTIC_LOOP_INPUT_PORTS = [
    ("unread_messages", "Any"),
    ("todo", "Any"),
]

AGENTIC_LOOP_OUTPUT_PORTS = [
    ("data", "Any"),
    ("error", "Any"),
]

logger = setup_colored_logging(logging.DEBUG)


def _get_background_loop(
    params: dict[str, Any],
) -> asyncio.AbstractEventLoop:
    """
    Resolve the executor loop used by the graph runtime.
    """
    executor = params.get("_executor")

    background_loop = (
        getattr(executor, "_loop", None)
        if executor is not None
        else None
    )

    if background_loop is None:
        background_loop = (
            params.get("_executor_loop")
            or params.get("_background_loop")
        )

    if not isinstance(
        background_loop,
        asyncio.AbstractEventLoop,
    ):
        raise TypeError(
            "AgenticLoop: background event loop not provided. Pass params['_executor'] or params['_executor_loop']."
        )

    return background_loop


def _fire_and_forget(
    coroutine: Any,
    background_loop: asyncio.AbstractEventLoop,
) -> None:
    future: Future[Any] = asyncio.run_coroutine_threadsafe(
        coroutine,
        background_loop,
    )

    def on_done(done_future: Future[Any]) -> None:
        try:
            done_future.result()
        except Exception:
            logger.exception("Agentic turn failed")

    future.add_done_callback(on_done)


def _agentic_loop_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any] | None,
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    del dt

    if state is None:
        state = {}

    state.setdefault("total_turns", 0)
    state.setdefault("total_errors", 0)

    unread_messages = inputs.get("unread_messages")
    todo = inputs.get("todo")

    unread_provided = unread_messages is not None
    todo_provided = todo is not None

    if unread_provided and todo_provided:
        state["total_errors"] += 1
        return (
            {
                "data": None,
                "error": {
                    "type": "error",
                    "error": (
                        "Provide only one of 'unread_messages' "
                        "or 'todo'"
                    ),
                },
            },
            state,
        )

    if not unread_provided and not todo_provided:
        return (
            {
                "data": {
                    "status": "idle",
                    "total_turns": state["total_turns"],
                    "total_errors": state["total_errors"],
                },
                "error": None,
            },
            state,
        )

    if unread_provided:
        if not isinstance(unread_messages, list):
            state["total_errors"] += 1
            return (
                {
                    "data": None,
                    "error": {
                        "type": "error",
                        "error": "unread_messages must be a list",
                    },
                },
                state,
            )

        if not all(
            isinstance(message, dict)
            for message in unread_messages
        ):
            state["total_errors"] += 1
            return (
                {
                    "data": None,
                    "error": {
                        "type": "error",
                        "error": (
                            "Every item in unread_messages "
                            "must be an object"
                        ),
                    },
                },
                state,
            )

        coroutine = run_agentic_turn(
            unread_chats=unread_messages,
        )
        input_kind = "unread_messages"
        input_count = len(unread_messages)

    else:
        if not isinstance(todo, list):
            state["total_errors"] += 1
            return (
                {
                    "data": None,
                    "error": {
                        "type": "error",
                        "error": "todo must be a list",
                    },
                },
                state,
            )

        if not all(
            isinstance(task, dict)
            for task in todo
        ):
            state["total_errors"] += 1
            return (
                {
                    "data": None,
                    "error": {
                        "type": "error",
                        "error": (
                            "Every item in todo must be an object"
                        ),
                    },
                },
                state,
            )

        coroutine = run_agentic_turn(
            incomplete_tasks=todo,
        )
        input_kind = "todo"
        input_count = len(todo)

    background_loop = _get_background_loop(params)
    _fire_and_forget(coroutine, background_loop)

    state["total_turns"] += 1

    logger.info(
        "Agentic turn triggered: input=%s count=%d",
        input_kind,
        input_count,
    )

    return (
        {
            "data": {
                "status": "triggered",
                "input": input_kind,
                "count": input_count,
                "total_turns": state["total_turns"],
                "total_errors": state["total_errors"],
            },
            "error": None,
        },
        state,
    )


def register_agentic_loop() -> None:
    register_unit(
        UnitSpec(
            type_name="AgenticLoop",
            input_ports=AGENTIC_LOOP_INPUT_PORTS,
            output_ports=AGENTIC_LOOP_OUTPUT_PORTS,
            step_fn=_agentic_loop_step,
            environment_tags=["taskvector"],
            environment_tags_are_agnostic=False,
            description=(
                "Triggers an agentic turn from either unread_messages "
                "or todo input. Exactly one input must be provided."
            ),
        )
    )


__all__ = [
    "AGENTIC_LOOP_INPUT_PORTS",
    "AGENTIC_LOOP_OUTPUT_PORTS",
    "register_agentic_loop",
]
