from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from runtime.executor import GraphWakeupCallback, GraphWakeupEvent
from services.logging import setup_colored_logging
from services.zmq.zmq_messaging import ZmqPublisher, ZmqTopics
from units.registry import UnitSpec, register_unit

logger = setup_colored_logging(logging.DEBUG)


ZMQ_OUT_INPUT_PORTS = [
    ("token", "Any"),
    ("job", "Any"),
    ("result", "Any"),
    ("update_batch", "Any"),
    ("error", "Any"),
]


ZMQ_OUT_OUTPUT_PORTS = [
    ("last_published", "Any"),
    ("error", "str"),
]


_OUTPUT_NAMES = (
    "token",
    "job",
    "result",
    "update_batch",
    "error",
)


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
            "ZmqOut: background event loop not provided. Pass params['_executor'], params['_executor_loop'], or params['_background_loop']."
        )

    if not background_loop.is_running():
        raise RuntimeError(
            "ZmqOut: background event loop is not running"
        )

    return background_loop


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


def _topic_value(
    *,
    topics: ZmqTopics,
    output_name: str,
) -> str:
    return str(getattr(topics, output_name))



def _close_publisher(state: dict[str, Any]) -> None:
    publisher = state.pop("_publisher", None)

    if publisher is None:
        return

    sock = getattr(publisher, "sock", None)

    if sock is not None:
        try:
            sock.close()
        except Exception:
            logger.exception("Failed closing ZmqOut publisher")


def _get_or_create_publisher(
    *,
    params: dict[str, Any],
    state: dict[str, Any],
    endpoint: str,
    topics: ZmqTopics,
) -> ZmqPublisher:
    publisher = state.get("_publisher")

    if (
        publisher is not None
        and state.get("_publisher_endpoint") == endpoint
    ):
        # Reuse the existing socket. The topics object does not determine
        # whether the publisher must be recreated.
        publisher.topics = topics
        return publisher

    if publisher is not None:
        _close_publisher(state)

    publisher = ZmqPublisher(
        pub_endpoint=endpoint,
        topics=topics,
        linger_ms=int(params.get("linger_ms", 0)),
        send_timeout_ms=int(params.get("send_timeout_ms", 5000)),
        slow_joiner_seconds=float(
            params.get("slow_joiner_seconds", 0.5)
        ),
    )

    state["_publisher"] = publisher
    state["_publisher_endpoint"] = endpoint

    return publisher



def _publish(
    *,
    params: dict[str, Any],
    state: dict[str, Any],
    output_name: str,
    payload: Any,
) -> None:
    endpoint = params.get("zmq_pub_endpoint")

    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError(
            "ZmqOut requires params['zmq_pub_endpoint']"
        )

    if not isinstance(payload, dict):
        raise TypeError(
            f"ZmqOut input '{output_name}' must be a dict because ZmqPublisher.publish expects a dict payload"
        )

    topics = _topics_from_params(params)

    publisher = _get_or_create_publisher(
        params=params,
        state=state,
        endpoint=endpoint,
        topics=topics,
    )

    publisher.publish(
        _topic_value(
            topics=topics,
            output_name=output_name,
        ),
        payload,
    )

    state["_last_published"] = {
        "topic": output_name,
        "message": payload,
    }

    state["_sequence"] = int(state.get("_sequence", 0)) + 1

    callback: GraphWakeupCallback | None = params.get(
        "_graph_wakeup_callback"
    )
    unit_id = params.get("_unit_id")

    if callback is not None and isinstance(unit_id, str) and unit_id:
        callback(
            GraphWakeupEvent(
                unit_id=unit_id,
                payload={
                    "topic": "last_published",
                    "message": state["_last_published"],
                },
                seq=state["_sequence"],
            )
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
            logger.debug("ZmqOut background operation was cancelled")
        except Exception:
            logger.exception("ZmqOut background operation failed")

    future.add_done_callback(_done_callback)


async def _publish_async(
    *,
    params: dict[str, Any],
    state: dict[str, Any],
    output_name: str,
    payload: Any,
) -> None:
    await asyncio.to_thread(
        _publish,
        params=params,
        state=state,
        output_name=output_name,
        payload=payload,
    )



def _zmq_out_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    del dt

    if state is None:
        state = {}

    _ = state.setdefault("_publisher", None)
    _ = state.setdefault("_publisher_endpoint", None)
    _ = state.setdefault("_last_published", None)
    state.setdefault("_sequence", 0)
    state.setdefault("publishing", False)


    # Expose the result of the previous asynchronous publication.
    last_published = state.pop("_last_published", None)

    provided = [
        (name, inputs.get(name))
        for name in _OUTPUT_NAMES
        if inputs.get(name) is not None
    ]

    if len(provided) > 1:
        return {
            "last_published": last_published,
            "error": (
                "Provide only one payload input at a time: "
                "token, job, result, update_batch, or error"
            ),
        }, state

    if not provided:
        return {
            "last_published": last_published,
            "error": None,
        }, state

    if state.get("publishing"):
        return {
            "last_published": last_published,
            "error": "A ZMQ publication is already in progress",
        }, state

    try:
        background_loop = _get_background_loop(params)
        output_name, payload = provided[0]

        state["publishing"] = True

        async def publish_and_mark_complete() -> None:
            try:
                await _publish_async(
                    params=params,
                    state=state,
                    output_name=output_name,
                    payload=payload,
                )
            except (
                OSError,
                ConnectionError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                state["_publish_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                state["publishing"] = False

        _fire_and_forget(
            publish_and_mark_complete(),
            background_loop,
        )

        return {
            "last_published": last_published,
            "error": None,
        }, state

    except (
        OSError,
        ConnectionError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        state["publishing"] = False

        return {
            "last_published": last_published,
            "error": f"{type(exc).__name__}: {exc}",
        }, state


def register_zmq_out_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="ZmqOut",
            input_ports=ZMQ_OUT_INPUT_PORTS,
            output_ports=ZMQ_OUT_OUTPUT_PORTS,
            step_fn=_zmq_out_step,
            environment_tags=["network"],
            environment_tags_are_agnostic=False,
            supports_graph_wakeup=True,
            description=(
                "Generic ZMQ PUB transport unit. Publishes one payload "
                "from token, job, result, update_batch, or error using "
                "params['zmq_pub_endpoint']."
            ),
        )
    )


__all__ = [
    "ZMQ_OUT_INPUT_PORTS",
    "ZMQ_OUT_OUTPUT_PORTS",
    "register_zmq_out_unit",
]
