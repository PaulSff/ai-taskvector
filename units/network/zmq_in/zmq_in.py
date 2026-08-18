"""
ZmqIn unit.

The ZmqIn unit subscribes to one or more ZeroMQ endpoints and exposes
received messages through graph output ports.

Supported output ports are:

    token
    job
    result
    update_batch
    error

The unit accepts two control inputs:

    {"action": "start"}
    {"action": "stop"}

A start command creates and starts the configured ZeroMQ subscribers.
A stop command stops and closes the subscribers. Repeated start commands
do not intentionally create another subscriber set while the unit is
marked as running.

Endpoints can be configured in either of two ways:

    params["endpoint"]

or:

    params["subscriptions_json_path"]

The JSON configuration may contain endpoint-specific topic selections.
When no JSON configuration is provided, the unit subscribes to all topics
defined by the injected ``ZmqTopics`` object.

The executor must inject the following runtime parameters:

    params["_unit_id"]
    params["_graph_wakeup_callback"]
    params["_executor"]

The receive handlers store the latest received message for each output
topic and invoke the graph wakeup callback. The callback emits a
``GraphWakeupEvent`` whose payload identifies the output topic and
message:

    GraphWakeupEvent(
        unit_id=unit_id,
        payload={
            "topic": output_name,
            "message": payload,
        },
        seq=sequence,
    )

The executor uses this event to rerun the ZmqIn unit and its downstream
workflow. On rerun, the unit returns the latest received value through
the corresponding output port.

Only the latest message per output topic is retained between executions.
If multiple messages arrive before the graph is rerun, earlier messages
for the same topic may be replaced by newer messages.

Subscribers and their asynchronous operations are kept in runtime state.
They must be stopped and closed when the unit stops or when the graph is
shut down. The unit requires a running background event loop supplied
through the executor or one of the supported loop parameters.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Coroutine
from typing import Any, Literal

from runtime.executor import GraphWakeupCallback, GraphWakeupEvent
from services.logging import setup_colored_logging
from services.zmq.zmq_messaging import ZmqTopics
from services.zmq.zmq_subscriber import ZmqSubscriber, ZmqSubscriptionConfig
from units.registry import UnitSpec, register_unit

logger = setup_colored_logging(logging.DEBUG)


# Inputs are control inputs only. Received ZMQ messages are outputs.
ZMQ_IN_INPUT_PORTS = [
    ("start", "Any"),
    ("stop", "Any"),
]


ZMQ_IN_OUTPUT_PORTS = [
    ("token", "Any"),
    ("job", "Any"),
    ("result", "Any"),
    ("update_batch", "Any"),
    ("error", "Any"),
]


Status = Literal["running", "stopped", "starting", "stopping"]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_background_loop(
    params: dict[str, Any],
) -> asyncio.AbstractEventLoop:
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

    if not isinstance(background_loop, asyncio.AbstractEventLoop):
        raise TypeError(
            "ZmqIn: background event loop not provided. Pass params['_executor'], params['_executor_loop'], or params['_background_loop']."
        )

    if not background_loop.is_running():
        raise RuntimeError("ZmqIn: background event loop is not running")

    return background_loop


def _load_subscriptions_from_json(
    path: str,
) -> list[tuple[str, str, tuple[str, ...]]]:
    """
    Expected JSON format:

    {
      "subscriptions": [
        {
          "name": "jobs",
          "sub_endpoint": "tcp://127.0.0.1:5555",
          "topic_idx": "0"
        }
      ],
      "topics": ["job", "result"]
    }
    """
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        return []

    topics = data.get("topics") or []
    subscriptions = data.get("subscriptions") or []

    if not isinstance(topics, list):
        return []

    if not isinstance(subscriptions, list):
        return []

    parsed: list[tuple[str, str, tuple[str, ...]]] = []

    for item in subscriptions:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        endpoint = item.get("sub_endpoint")
        topic_idx = item.get("topic_idx")

        if not isinstance(name, str):
            continue

        if not isinstance(endpoint, str) or not endpoint.strip():
            continue

        index: int | None = None

        if isinstance(topic_idx, int):
            index = topic_idx
        elif isinstance(topic_idx, str):
            try:
                index = int(topic_idx)
            except ValueError:
                continue

        if index is None or index < 0 or index >= len(topics):
            continue

        topic_name = topics[index]

        if not isinstance(topic_name, str):
            continue

        parsed.append((name, endpoint, (topic_name,)))

    return parsed


def _infer_endpoints_from_params(
    params: dict[str, Any],
) -> tuple[list[str], str | None]:
    subscriptions_json_path = params.get("subscriptions_json_path")
    endpoint = params.get("endpoint")

    json_path_used: str | None = None
    endpoints: list[str] = []

    if (
        isinstance(subscriptions_json_path, str)
        and subscriptions_json_path.strip()
    ):
        json_path_used = subscriptions_json_path

        parsed = _load_subscriptions_from_json(
            subscriptions_json_path,
        )

        endpoints = [
            endpoint
            for (_name, endpoint, _topics) in parsed
        ]

    elif isinstance(endpoint, str) and endpoint.strip():
        endpoints = [endpoint]

    deduped: list[str] = []
    seen: set[str] = set()

    for item in endpoints:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    return deduped, json_path_used


def _topics_from_params(params: dict[str, Any]) -> ZmqTopics:
    injected = params.get("topics")

    required_attributes = (
        "token",
        "job",
        "result",
        "update_batch",
        "error",
    )

    if injected is not None and all(
        hasattr(injected, attribute)
        for attribute in required_attributes
    ):
        return injected  # type: ignore[return-value]

    return ZmqTopics()


def _all_unit_topic_names(topics: ZmqTopics) -> list[str]:
    return [
        topics.token,
        topics.job,
        topics.result,
        topics.update_batch,
        topics.error,
    ]


def _make_wakeup_handler(
    *,
    state: dict[str, Any],
    output_name: str,
    unit_id: str,
    callback: GraphWakeupCallback | None,
):
    async def _handler(_topic: str, payload: Any) -> None:
        latest = state.setdefault("_latest", {})
        latest[output_name] = payload

        state["_sequence"] = (
            _safe_int(state.get("_sequence"), default=0) + 1
        )
        state["total_messages"] = (
            _safe_int(state.get("total_messages"), default=0) + 1
        )

        if callback is None:
            return

        callback(
            GraphWakeupEvent(
                unit_id=unit_id,
                payload={
                    "topic": output_name,
                    "message": payload,
                },
                seq=state["_sequence"],
            )
        )

    return _handler


def _register_handlers(
    *,
    subscriber: ZmqSubscriber,
    topics: ZmqTopics,
    state: dict[str, Any],
    unit_id: str,
    callback: GraphWakeupCallback | None,
) -> None:
    topic_handlers = (
        (topics.token, "token"),
        (topics.job, "job"),
        (topics.result, "result"),
        (topics.update_batch, "update_batch"),
        (topics.error, "error"),
    )

    for zmq_topic, output_name in topic_handlers:
        subscriber.on(
            zmq_topic,
            _make_wakeup_handler(
                state=state,
                output_name=output_name,
                unit_id=unit_id,
                callback=callback,
            ),
        )


def _fire_and_forget(
    coroutine: Coroutine[Any, Any, Any],
    background_loop: asyncio.AbstractEventLoop,
) -> None:
    future = asyncio.run_coroutine_threadsafe(
        coroutine,
        background_loop,
    )

    def _done_callback(done_future: Any) -> None:
        try:
            done_future.result()
        except asyncio.CancelledError:
            logger.debug("ZmqIn background operation was cancelled")
        except Exception:
            logger.exception("ZmqIn background operation failed")

    future.add_done_callback(_done_callback)


async def _maybe_start_subscribers(
    *,
    params: dict[str, Any],
    state: dict[str, Any],
) -> None:
    unit_id = params.get("_unit_id")

    callback: GraphWakeupCallback | None = params.get(
        "_graph_wakeup_callback"
    )

    if not isinstance(unit_id, str) or not unit_id:
        raise ValueError("ZmqIn requires params['_unit_id']")

    endpoints, json_path_used = _infer_endpoints_from_params(params)

    if not endpoints:
        raise ValueError(
            "No endpoint provided: set params['endpoint'] or params['subscriptions_json_path']."
        )

    topics = _topics_from_params(params)
    all_topics = _all_unit_topic_names(topics)
    accepted_topics = list(dict.fromkeys(all_topics))

    receive_timeout_ms = _safe_int(
        params.get("rcvtimeo_ms"),
        default=1000,
    )

    max_in_flight = max(
        1,
        _safe_int(
            params.get("max_in_flight_handlers"),
            default=32,
        ),
    )

    subscribers: list[ZmqSubscriber] = []
    state["_subscribers"] = subscribers

    try:
        if json_path_used:
            parsed = _load_subscriptions_from_json(json_path_used)

            for _name, endpoint, selected_topics in parsed:
                config = ZmqSubscriptionConfig(
                    sub_endpoint=endpoint,
                    topics=list(selected_topics),
                    accept_topics=accepted_topics,
                    rcvtimeo_ms=receive_timeout_ms,
                    max_in_flight_handlers=max_in_flight,
                )

                subscriber = ZmqSubscriber(
                    config=config,
                    loop=_get_background_loop(params),
                )

                _register_handlers(
                    subscriber=subscriber,
                    topics=topics,
                    state=state,
                    unit_id=unit_id,
                    callback=callback,
                )

                subscribers.append(subscriber)

        else:
            for endpoint in endpoints:
                config = ZmqSubscriptionConfig(
                    sub_endpoint=endpoint,
                    topics=all_topics,
                    accept_topics=accepted_topics,
                    rcvtimeo_ms=receive_timeout_ms,
                    max_in_flight_handlers=max_in_flight,
                )

                subscriber = ZmqSubscriber(
                    config=config,
                    loop=_get_background_loop(params),
                )

                _register_handlers(
                    subscriber=subscriber,
                    topics=topics,
                    state=state,
                    unit_id=unit_id,
                    callback=callback,
                )

                subscribers.append(subscriber)

        for subscriber in subscribers:
            await subscriber.start()

        state["running"] = True
        state["started_at"] = state.get("started_at") or asyncio.get_running_loop().time()

    except Exception:
        for subscriber in subscribers:
            try:
                subscriber.close()
            except Exception:
                logger.exception("Failed closing ZmqIn subscriber")

        state["_subscribers"] = []
        state["running"] = False
        raise


async def _maybe_stop_subscribers(
    *,
    state: dict[str, Any],
) -> None:
    subscribers: list[ZmqSubscriber] = list(
        state.get("_subscribers") or []
    )

    try:
        for subscriber in subscribers:
            try:
                await subscriber.stop()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed stopping ZmqIn subscriber")

        for subscriber in subscribers:
            try:
                subscriber.close()
            except Exception:
                logger.exception("Failed closing ZmqIn subscriber")

    finally:
        state["_subscribers"] = []
        state["running"] = False


def _emit_latest_and_clear(
    state: dict[str, Any],
) -> dict[str, Any]:
    latest = state.pop("_latest", {})

    return {
        "token": latest.get("token"),
        "job": latest.get("job"),
        "result": latest.get("result"),
        "update_batch": latest.get("update_batch"),
        "error": latest.get("error"),
    }


def _empty_outputs() -> dict[str, Any]:
    return {
        "token": None,
        "job": None,
        "result": None,
        "update_batch": None,
        "error": None,
    }


def _zmq_in_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    del dt

    if state is None:
        state = {}

    state.setdefault("running", False)
    state.setdefault("started_at", None)
    state.setdefault("total_messages", 0)
    state.setdefault("total_errors", 0)
    state.setdefault("stop_requested", False)
    state.setdefault("_subscribers", [])
    state.setdefault("_latest", {})
    state.setdefault("_sequence", 0)

    try:
        background_loop = _get_background_loop(params)

        start_payload = inputs.get("start")
        stop_payload = inputs.get("stop")

        if start_payload is not None and stop_payload is not None:
            return {
                **_empty_outputs(),
                "error": {
                    "type": "error",
                    "error": "Provide only one of start/stop",
                },
            }, state

        if stop_payload is not None:
            if not isinstance(stop_payload, dict):
                return {
                    **_empty_outputs(),
                    "error": {
                        "type": "error",
                        "error": "stop input must be a dict",
                    },
                }, state

            if stop_payload.get("action") != "stop":
                return {
                    **_empty_outputs(),
                    "error": {
                        "type": "error",
                        "error": (
                            f"Invalid stop.action="
                            f"{stop_payload.get('action')!r}"
                        ),
                    },
                }, state

            if state.get("running"):
                _fire_and_forget(
                    _maybe_stop_subscribers(state=state),
                    background_loop,
                )

            state["running"] = False
            state["stop_requested"] = True

            return _empty_outputs(), state

        if start_payload is not None:
            if not isinstance(start_payload, dict):
                return {
                    **_empty_outputs(),
                    "error": {
                        "type": "error",
                        "error": "start input must be a dict",
                    },
                }, state

            if start_payload.get("action") != "start":
                return {
                    **_empty_outputs(),
                    "error": {
                        "type": "error",
                        "error": (
                            f"Invalid start.action="
                            f"{start_payload.get('action')!r}"
                        ),
                    },
                }, state

            if not state.get("running"):
                state["stop_requested"] = False
                state["running"] = True

                _fire_and_forget(
                    _maybe_start_subscribers(
                        params=params,
                        state=state,
                    ),
                    background_loop,
                )

            return _emit_latest_and_clear(state), state

        # Messages received by ZMQ are stored by the receive handler.
        # The wakeup callback causes the executor to rerun this unit.
        return _emit_latest_and_clear(state), state

    except (OSError, ConnectionError, RuntimeError, TypeError, ValueError) as exc:
        state["total_errors"] = (
            _safe_int(state.get("total_errors"), default=0) + 1
        )

        return {
            **_empty_outputs(),
            "error": {
                "type": "error",
                "error": f"{type(exc).__name__}: {exc}",
            },
        }, state


def register_zmq_in_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="ZmqIn",
            input_ports=ZMQ_IN_INPUT_PORTS,
            output_ports=ZMQ_IN_OUTPUT_PORTS,
            step_fn=_zmq_in_step,
            environment_tags=["network"],
            environment_tags_are_agnostic=False,
            description=(
                "Generic ZMQ SUB transport unit powered by ZmqSubscriber. "
                "Received messages wake the graph through the injected "
                "_graph_wakeup_callback. Configure either endpoint or "
                "subscriptions_json_path."
            ),
        )
    )


__all__ = [
    "ZMQ_IN_INPUT_PORTS",
    "ZMQ_IN_OUTPUT_PORTS",
    "register_zmq_in_unit",
]
