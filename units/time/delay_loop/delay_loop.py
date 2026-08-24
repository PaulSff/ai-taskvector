"""
DelayLoop unit.

The DelayLoop unit periodically emits a payload and wakes the graph
executor before each emission. The payload is read from the ``payload``
input port when provided; otherwise, it is read from
``params["payload"]``.

The loop is controlled through the ``control`` input port:

    {"action": "start"}
    {"action": "stop"}

When started, the unit waits for ``update_interval_s`` seconds, emits the
configured payload through the ``out`` output port, and repeats until it
receives a stop command.

Each timer tick invokes the graph wakeup callback with an event payload
compatible with the unit's ``payload`` input port:

    GraphWakeupEvent(
        unit_id=unit_id,
        payload={"payload": configured_payload},
        seq=sequence,
    )

The executor then reruns this unit and propagates its ``out`` output to
downstream units.

Runtime timer tasks are kept outside serialized unit state so repeated
calls to ``step_fn`` do not create duplicate timer tasks. Starting an
already-running loop is idempotent. The graph or executor should stop
active DelayLoop tasks during shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from runtime.executor import GraphWakeupCallback, GraphWakeupEvent
from services.logging import setup_colored_logging
from units.registry import UnitSpec, register_unit

DEFAULT_UPDATE_INTERVAL_S = 1.0

logger = setup_colored_logging(logging.DEBUG)


DELAY_LOOP_INPUT_PORTS = [
    ("control", "Any"),
    ("payload", "Any"),
]


DELAY_LOOP_OUTPUT_PORTS = [
    ("out", "Any"),
    ("error", "Any"),
]


# Runtime-only resources. Do not put asyncio tasks in serialized unit state.
_DELAY_TASKS: dict[str, asyncio.Task[Any]] = {}
_DELAY_STOPS: dict[str, asyncio.Event] = {}


def _empty_outputs() -> dict[str, Any]:
    return {
        "out": None,
        "error": None,
    }


def _get_background_loop(
    params: dict[str, Any],
) -> asyncio.AbstractEventLoop:
    executor = params.get("_executor")

    loop = (
        getattr(executor, "_loop", None)
        if executor is not None
        else None
    )

    if loop is None:
        loop = (
            params.get("_executor_loop")
            or params.get("_background_loop")
        )

    if not isinstance(loop, asyncio.AbstractEventLoop):
        raise TypeError(
            "DelayLoop requires params['_executor'], params['_executor_loop'], or params['_background_loop']"
        )

    if not loop.is_running():
        raise RuntimeError("DelayLoop background event loop is not running")

    return loop


def _get_interval(params: dict[str, Any]) -> float:
    value = params.get("update_interval_s", DEFAULT_UPDATE_INTERVAL_S)

    try:
        interval = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "update_interval_s must be a positive number"
        ) from exc

    if interval <= 0:
        raise ValueError("update_interval_s must be greater than zero")

    return interval


def _get_payload(
    params: dict[str, Any],
    inputs: dict[str, Any],
) -> Any:
    # An explicitly supplied input takes precedence over params.
    if inputs.get("payload") is not None:
        return inputs["payload"]

    if "payload" in params:
        return params["payload"]

    return None


def _emit_wakeup(
    *,
    unit_id: str,
    callback: GraphWakeupCallback | None,
    sequence: int,
    payload: Any,
) -> None:
    if callback is None:
        return

    callback(
        GraphWakeupEvent(
            unit_id=unit_id,
            payload={
                "payload": payload,
            },
            seq=sequence,
        )
    )


async def _delay_loop(
    *,
    unit_id: str,
    interval_s: float,
    payload: Any,
    stop_event: asyncio.Event,
    callback: GraphWakeupCallback | None,
) -> None:
    sequence = 0

    try:
        logger.debug(
            "DelayLoop task started: unit=%s interval=%s payload=%r callback=%r",
            unit_id,
            interval_s,
            payload,
            callback,
        )

        # Emit the first item immediately on start.
        if stop_event.is_set():
            return

        sequence += 1

        # logger.debug(
        #    "DelayLoop emitting initial wakeup: unit=%s sequence=%s payload=%r",
        #    unit_id,
        #    sequence,
        #    payload,
        # )

        _emit_wakeup(
            unit_id=unit_id,
            callback=callback,
            sequence=sequence,
            payload=payload,
        )

        # Emit subsequent items at the configured interval.
        while True:
            try:
                _ = await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=interval_s,
                )
                logger.debug("DelayLoop stopped: unit=%s", unit_id)
                return
            except TimeoutError:
                logger.debug("DelayLoop timeout fired: unit=%s", unit_id)

            if stop_event.is_set():
                return

            sequence += 1

            # logger.debug(
            #     "DelayLoop emitting wakeup: unit=%s sequence=%s payload=%r",
            #   unit_id,
            #   sequence,
            #    payload,
            # )

            _emit_wakeup(
                unit_id=unit_id,
                callback=callback,
                sequence=sequence,
                payload=payload,
            )

    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "DelayLoop timer failed for unit %s",
            unit_id,
        )


async def _stop_loop(unit_id: str) -> None:
    stop_event = _DELAY_STOPS.pop(unit_id, None)
    task = _DELAY_TASKS.pop(unit_id, None)

    if stop_event is not None:
        stop_event.set()

    if task is not None and task is not asyncio.current_task():
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _start_loop(
    *,
    unit_id: str,
    interval_s: float,
    payload: Any,
    callback: GraphWakeupCallback | None,
) -> None:
    # Make start idempotent.
    if unit_id in _DELAY_TASKS:
        return

    stop_event = asyncio.Event()

    task = asyncio.create_task(
        _delay_loop(
            unit_id=unit_id,
            interval_s=interval_s,
            payload=payload,
            stop_event=stop_event,
            callback=callback,
        ),
        name=f"DelayLoop:{unit_id}",
    )

    _DELAY_STOPS[unit_id] = stop_event
    _DELAY_TASKS[unit_id] = task


def _schedule_coroutine(
    coroutine: Any,
    loop: asyncio.AbstractEventLoop,
) -> None:
    future = asyncio.run_coroutine_threadsafe(coroutine, loop)

    def done_callback(done_future: Any) -> None:
        try:
            done_future.result()
        except asyncio.CancelledError:
            logger.debug("DelayLoop operation was cancelled")
        except Exception:
            logger.exception("DelayLoop operation failed")

    future.add_done_callback(done_callback)


def _delay_loop_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    del dt

    if state is None:
        state = {}

    state.setdefault("running", False)
    state.setdefault("total_ticks", 0)
    state.setdefault("total_errors", 0)
    state.setdefault("last_tick_at", None)

    unit_id = params.get("_unit_id")
    callback: GraphWakeupCallback | None = params.get(
        "_graph_wakeup_callback"
    )

    if not isinstance(unit_id, str) or not unit_id:
        return {
            **_empty_outputs(),
            "error": {
                "type": "error",
                "error": "DelayLoop requires params['_unit_id']",
            },
        }, state

    try:
        loop = _get_background_loop(params)
        interval_s = _get_interval(params)

        control = inputs.get("control")

        if control is not None:
            if not isinstance(control, dict):
                return {
                    **_empty_outputs(),
                    "error": {
                        "type": "error",
                        "error": (
                            "control input must be "
                            "{'action': 'start'} or {'action': 'stop'}"
                        ),
                    },
                }, state

            action = control.get("action")

            if action == "start":
                logger.debug(
                    "DelayLoop received start: unit=%s control=%r",
                    unit_id,
                    control,
                )

                payload = _get_payload(params, inputs)

                if unit_id not in _DELAY_TASKS:
                    _schedule_coroutine(
                        _start_loop(
                            unit_id=unit_id,
                            interval_s=interval_s,
                            payload=payload,
                            callback=callback,
                        ),
                        loop,
                    )

                state["running"] = True

            elif action == "stop":
                logger.debug(
                    "DelayLoop received stop: unit=%s control=%r",
                    unit_id,
                    control,
                )

                _schedule_coroutine(
                    _stop_loop(unit_id),
                    loop,
                )

                state["running"] = False

            else:
                return {
                    **_empty_outputs(),
                    "error": {
                        "type": "error",
                        "error": (
                            "control action must be either "
                            "'start' or 'stop'"
                        ),
                    },
                }, state

        # The wakeup event stores the timer payload under the `payload`
        # input name. Returning it here propagates it downstream.
        payload = inputs.get("payload")

        if payload is not None:
            state["total_ticks"] += 1
            state["last_tick_at"] = time.time()

            return {
                "out": payload,
                "error": None,
            }, state

        return _empty_outputs(), state

    except (TypeError, ValueError, RuntimeError, OSError) as exc:
        state["total_errors"] += 1

        return {
            **_empty_outputs(),
            "error": {
                "type": "error",
                "error": f"{type(exc).__name__}: {exc}",
            },
        }, state


def register_delay_loop_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="DelayLoop",
            input_ports=DELAY_LOOP_INPUT_PORTS,
            output_ports=DELAY_LOOP_OUTPUT_PORTS,
            step_fn=_delay_loop_step,
            environment_tags=["time"],
            environment_tags_are_agnostic=False,
            supports_graph_wakeup=True,
            description=(
                "Periodically wakes the graph and emits a configured "
                "or input payload."
            ),
        )
    )

__all__ = [
    "DELAY_LOOP_INPUT_PORTS",
    "DELAY_LOOP_OUTPUT_PORTS",
    "register_delay_loop_unit",
]
