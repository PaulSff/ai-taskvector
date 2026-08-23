"""
ZmqOut Unis is a queued publisher with an explicit control input.

payload arrives
  → validate
  → append to queue
  → emit action-only callback

callback arrives with action=publish
  → clear pending flag
  → pop one item
  → publish asynchronously

publication completes
  → if queue is nonempty, emit another action-only callback

For example:
    update_batch payload
        → validate
        → enqueue
        → executor callback with {"action": {"action": "publish"}}
        → publish one queued item
        → callback again if more items remain

Three cases to handle:

payload only
    → enqueue payload
    → emit publish callback

action only + queue has item
    → pop and publish queued item

payload + action
    → enqueue payload
    → emit publish callback
    → process the action against the queue

Anti-spam protection: duplicated input payload is ignored.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from copy import deepcopy
from typing import Any

from runtime.executor import GraphWakeupCallback, GraphWakeupEvent
from services.logging import setup_colored_logging
from services.zmq.zmq_messaging import ZmqPublisher, ZmqTopics
from units.network.zmq_out.helpers import (
    bool_or_default,
    is_empty_value,
    optional_dict,
    optional_float,
    optional_process_graph,
    optional_str,
    required_dict,
    required_str,
)
from units.registry import UnitSpec, register_unit

logger = setup_colored_logging(logging.DEBUG)


ZMQ_OUT_INPUT_PORTS = [
    ("action", "Any"),
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


_PAYLOAD_INPUT_NAMES = (
    "token",
    "job",
    "result",
    "update_batch",
    "error",
)


_PUBLISH_ACTION = {
    "action": "publish",
}


def _get_background_loop(
    params: dict[str, object],
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


def _topics_from_params(params: dict[str, object]) -> ZmqTopics:
    injected = params.get("topics")

    if isinstance(injected, ZmqTopics):
        return injected

    return ZmqTopics()


def _close_publisher(state: dict[str, object]) -> None:
    publisher = state.pop("_publisher", None)

    if publisher is None:
        return

    if not isinstance(publisher, ZmqPublisher):
        raise TypeError(
            f"'_publisher' must be ZmqPublisher, got {type(publisher).__name__}"
        )

    try:
        publisher.sock.close()
    except Exception:
        logger.exception("Failed closing ZmqOut publisher")


def _as_int(value: object, default: int) -> int:
    if isinstance(value, (int, str)):
        return int(value)

    return default


def _as_float(value: object, default: float) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)

    return default


def _get_or_create_publisher(
    *,
    params: dict[str, object],
    state: dict[str, object],
    endpoint: str,
    topics: ZmqTopics,
) -> ZmqPublisher:
    injected_publisher = state.get("_publisher")

    if (
        isinstance(injected_publisher, ZmqPublisher)
        and state.get("_publisher_endpoint") == endpoint
    ):
        injected_publisher.topics = topics
        return injected_publisher

    if injected_publisher is not None:
        _close_publisher(state)

    publisher = ZmqPublisher(
        pub_endpoint=endpoint,
        topics=topics,
        linger_ms=_as_int(params.get("linger_ms"), 0),
        send_timeout_ms=_as_int(params.get("send_timeout_ms"), 5000),
        slow_joiner_seconds=_as_float(
            params.get("slow_joiner_seconds"),
            0.5,
        ),
    )

    state["_publisher"] = publisher
    state["_publisher_endpoint"] = endpoint

    return publisher


def _validate_job_payload(
    payload: dict[str, object],
) -> None:
    run_id = payload.get("run_id")

    if not isinstance(run_id, str) or not run_id:
        raise ValueError(
            "job payload requires a non-empty 'run_id: str'"
        )

    workflow_path = payload.get("workflow_path")
    workflow_graph = payload.get("workflow_graph")

    if (workflow_path is None) == (workflow_graph is None):
        raise ValueError(
            "job payload must provide exactly one of 'workflow_path' or 'workflow_graph'"
        )

    if workflow_path is not None and not isinstance(
        workflow_path,
        str,
    ):
        raise ValueError(
            "job 'workflow_path' must be a string"
        )

    if workflow_graph is not None and not isinstance(
        workflow_graph,
        dict,
    ):
        raise ValueError(
            "job 'workflow_graph' must be a dictionary"
        )

    for field_name in (
        "initial_inputs",
        "unit_param_overrides",
    ):
        value = payload.get(field_name)

        if value is not None and not isinstance(value, dict):
            raise ValueError(
                f"job '{field_name}' must be a dictionary"
            )

    for field_name in (
        "format",
        "response_endpoint",
        "update_endpoint",
    ):
        value = payload.get(field_name)

        if value is not None and not isinstance(value, str):
            raise ValueError(
                f"job '{field_name}' must be a string"
            )

    timeout = payload.get("execution_timeout_s")

    if timeout is not None and not isinstance(
        timeout,
        (int, float),
    ):
        raise ValueError(
            "job 'execution_timeout_s' must be numeric"
        )

    keep_alive = payload.get("keep_alive")

    if keep_alive is not None and not isinstance(
        keep_alive,
        bool,
    ):
        raise ValueError(
            "job 'keep_alive' must be a boolean"
        )

def _validate_payload(
    output_name: str,
    payload: Any,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError(
            f"ZmqOut input '{output_name}' must be a dict"
        )

    if is_empty_value(payload):
        raise ValueError(
            f"ZmqOut input '{output_name}' must contain at least one non-empty value"
        )

    if output_name == "job":
        _validate_job_payload(payload)

    elif output_name == "token":
        run_id = payload.get("run_id")
        token = payload.get("token")

        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or not isinstance(token, str)
            or not token.strip()
        ):
            raise ValueError(
                "token payload must contain non-empty 'run_id: str' and 'token: str'"
            )

    elif output_name == "result":
        run_id = payload.get("run_id")
        outputs = payload.get("outputs")

        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or not isinstance(outputs, dict)
        ):
            raise ValueError(
                "result payload must contain non-empty 'run_id: str' and 'outputs: dict'"
            )

    elif output_name == "error":
        run_id = payload.get("run_id")
        error = payload.get("error")

        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or not isinstance(error, str)
            or not error.strip()
        ):
            raise ValueError(
                "error payload must contain non-empty 'run_id: str' and 'error: str'"
            )

    elif output_name == "update_batch":
        # publish_update_batch accepts a dictionary.
        # The recursive empty-value check above rejects:
        # {}, {"update": "", "something": {}}, etc.
        pass

    else:
        raise ValueError(
            f"Unsupported ZMQ output '{output_name}'"
        )

    return payload


def _publish(
    *,
    params: dict[str, object],
    state: dict[str, object],
    output_name: str,
    payload: dict[str, object],
) -> None:
    logger.info(
        "ZmqOut publishing: output_name=%r endpoint=%r",
        output_name,
        params.get("zmq_pub_endpoint"),
    )

    endpoint = params.get("zmq_pub_endpoint")

    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError(
            "ZmqOut requires params['zmq_pub_endpoint']"
        )

    publisher = _get_or_create_publisher(
        params=params,
        state=state,
        endpoint=endpoint,
        topics=_topics_from_params(params),
    )

    if output_name == "job":
        publisher.publish_job(
            run_id=required_str(payload, "run_id"),
            workflow_path=optional_str(payload, "workflow_path"),
            workflow_graph=optional_process_graph(
                payload,
                "workflow_graph",
            ),
            format=optional_str(payload, "format"),
            initial_inputs=optional_dict(
                payload,
                "initial_inputs",
            ),
            unit_param_overrides=optional_dict(
                payload,
                "unit_param_overrides",
            ),
            response_endpoint=optional_str(
                payload,
                "response_endpoint",
            ),
            update_endpoint=optional_str(
                payload,
                "update_endpoint",
            ),
            execution_timeout_s=optional_float(
                payload,
                "execution_timeout_s",
            ),
            keep_alive=bool_or_default(
                payload,
                "keep_alive",
            ),
        )

    elif output_name == "token":
        publisher.publish_token(
            run_id=required_str(payload, "run_id"),
            token=required_str(payload, "token"),
        )

    elif output_name == "result":
        publisher.publish_result(
            run_id=required_str(payload, "run_id"),
            outputs=required_dict(payload, "outputs"),
        )

    elif output_name == "update_batch":
        publisher.publish_update_batch(payload)

    else:
        raise ValueError(
            f"No publisher method exists for {output_name!r}"
        )


async def _publish_async(
    *,
    params: dict[str, object],
    state: dict[str, object],
    output_name: str,
    payload: dict[str, Any],
) -> None:
    await asyncio.to_thread(
        _publish,
        params=params,
        state=state,
        output_name=output_name,
        payload=payload,
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
            logger.debug(
                "ZmqOut background operation was cancelled"
            )
        except Exception:
            logger.exception(
                "ZmqOut background operation failed"
            )

    future.add_done_callback(_done_callback)


def _emit_publish_action(
    *,
    params: dict[str, Any],
    state: dict[str, Any],
) -> None:
    callback: GraphWakeupCallback | None = params.get(
        "_graph_wakeup_callback"
    )
    unit_id = params.get("_unit_id")

    if callback is None:
        logger.error(
            "ZmqOut cannot emit publish callback: params['_graph_wakeup_callback'] is missing. params=%r",
            params,
        )
        return

    if not isinstance(unit_id, str) or not unit_id:
        logger.error(
            "ZmqOut cannot emit publish callback: params['_unit_id'] is missing or invalid: %r",
            unit_id,
        )
        return

    if state.get("_publish_action_pending") is True:
        logger.debug(
            "ZmqOut publish callback already pending for unit %s",
            unit_id,
        )
        return

    state["_publish_action_pending"] = True
    state["_sequence"] = int(
        state.get("_sequence", 0)
    ) + 1

    event = GraphWakeupEvent(
        unit_id=unit_id,
        payload={
            "action": {
                "action": "publish",
            },
        },
        seq=state["_sequence"],
    )

    logger.debug(
        "ZmqOut emitting publish callback: unit_id=%s event=%r",
        unit_id,
        event,
    )

    try:
        callback(event)
    except Exception:
        state["_publish_action_pending"] = False

        logger.exception(
            "ZmqOut graph wakeup callback failed"
        )

        raise


def _start_publication(
    *,
    params: dict[str, object],
    state: dict[str, object],
    item: dict[str, Any],
) -> None:
    background_loop = _get_background_loop(params)

    state["_publishing"] = True

    logger.debug(
        "ZmqOut starting publication: output_name=%r payload=%r",
        item.get("output_name"),
        item.get("payload"),
    )

    async def publish_and_mark_complete() -> None:
        try:
            await _publish_async(
                params=params,
                state=state,
                output_name=item["output_name"],
                payload=item["payload"],
            )

            logger.debug(
                "ZmqOut publication completed: output_name=%r",
                item.get("output_name"),
            )

        except Exception as exc:
            state["_publish_error"] = (
                f"{type(exc).__name__}: {exc}"
            )

            logger.exception(
                "ZmqOut publication failed: output_name=%r",
                item.get("output_name"),
            )

        finally:
            state["_publishing"] = False

            queue_value = state.get("_publish_queue")

            if not isinstance(queue_value, list):
                raise TypeError("'_publish_queue' must be a list")

            logger.debug(
                "ZmqOut publication cleanup: queue_size=%d",
                len(queue_value),
            )

            if state.get("_publish_queue"):
                _emit_publish_action(
                    params=params,
                    state=state,
                )

    _fire_and_forget(
        publish_and_mark_complete(),
        background_loop,
    )


def _handle_publish_action(
    *,
    params: dict[str, Any],
    state: dict[str, object],
    last_published: Any,
    previous_error: Any,
) -> tuple[dict[str, Any], dict[str, object]]:
    queue_value = state.get("_publish_queue")

    if not isinstance(queue_value, list):
        raise TypeError("'_publish_queue' must be a list")

    queue: list[dict[str, Any]] = queue_value

    logger.info(
        "ZmqOut received publish action: queue_size=%d publishing=%r",
        len(queue),
        state.get("_publishing"),
    )

    state["_publish_action_pending"] = False

    if not queue:
        return {
            "last_published": last_published,
            "error": previous_error,
        }, state

    if state.get("_publishing"):
        return {
            "last_published": last_published,
            "error": (
                "A ZMQ publication is already in progress"
            ),
        }, state

    item = queue.pop(0)

    try:
        _start_publication(
            params=params,
            state=state,
            item=item,
        )
    except (
        OSError,
        ConnectionError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        state["_publishing"] = False

        return {
            "last_published": last_published,
            "error": f"{type(exc).__name__}: {exc}",
        }, state

    return {
        "last_published": last_published,
        "error": previous_error,
    }, state



def _handle_payload_input(
    *,
    inputs: dict[str, object],
    params: dict[str, Any],
    state: dict[str, object],
    last_published: object,
    previous_error: object,
) -> tuple[dict[str, object], dict[str, object]]:
    provided = [
        (name, inputs[name])
        for name in _PAYLOAD_INPUT_NAMES
        if name in inputs and inputs[name] is not None
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
            "error": previous_error,
        }, state

    output_name, raw_payload = provided[0]

    # Block a duplicate before validation, queueing, callback emission,
    # or processing an accompanying action.
    previous_payload = state.get("_last_payload")

    if (
        isinstance(previous_payload, tuple)
        and len(previous_payload) == 2
        and previous_payload[0] == output_name
        and raw_payload == previous_payload[1]
    ):
        logger.warning(
            "ZmqOut blocked duplicate payload: output_name=%r",
            output_name,
        )

        return {
            "last_published": last_published,
            "error": previous_error,
            "duplicate_blocked": True,
        }, state

    try:
        payload = _validate_payload(
            output_name,
            raw_payload,
        )
    except (TypeError, ValueError) as exc:
        return {
            "last_published": last_published,
            "error": f"{type(exc).__name__}: {exc}",
        }, state

    queue_value = state.get("_publish_queue")

    if not isinstance(queue_value, list):
        raise TypeError("'_publish_queue' must be a list")

    queue: list[dict[str, Any]] = queue_value

    queue.append(
        {
            "output_name": output_name,
            "payload": payload,
        }
    )

    # Store only successfully validated and queued payloads.
    # deepcopy prevents later caller mutation from changing the comparison value.
    state["_last_payload"] = (
        output_name,
        deepcopy(payload),
    )

    # Request an action-only callback after successfully queueing
    # the validated payload.
    _emit_publish_action(
        params=params,
        state=state,
    )

    return {
        "last_published": last_published,
        "error": previous_error,
    }, state


def _zmq_out_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, object],
    dt: float,
) -> tuple[dict[str, Any], dict[str, object]]:
    del dt

    _ = state.setdefault("_publish_queue", [])
    _ = state.setdefault("_publishing", False)
    _ = state.setdefault("_publish_action_pending", False)
    _ = state.setdefault("_last_published", None)
    _ = state.setdefault("_publish_error", None)
    _ = state.setdefault("_last_payload", None)
    _ = state.setdefault("_sequence", 0)

    last_published = state.pop(
        "_last_published",
        None,
    )

    previous_error = state.pop(
        "_publish_error",
        None,
    )

    action = inputs.get("action")

    payload_present = any(
        name in inputs and inputs[name] is not None
        for name in _PAYLOAD_INPUT_NAMES
    )

    if payload_present:
        payload_outputs, state = _handle_payload_input(
            inputs=inputs,
            params=params,
            state=state,
            last_published=last_published,
            previous_error=previous_error,
        )

        # A duplicate payload blocks the entire step. In particular, an
        # accompanying publish action must not consume or publish anything.
        if payload_outputs.get("duplicate_blocked") is True:
            return {
                "last_published": last_published,
                "error": previous_error,
            }, state

        last_published = payload_outputs["last_published"]
        previous_error = payload_outputs["error"]

    # Payload only: it has been queued and its callback has been emitted.
    if action is None:
        return {
            "last_published": last_published,
            "error": previous_error,
        }, state

    # The action is never queued; it consumes one item from the queue.
    if action != _PUBLISH_ACTION:
        return {
            "last_published": last_published,
            "error": (
                "Invalid action; expected "
                "{'action': 'publish'}"
            ),
        }, state

    return _handle_publish_action(
        params=params,
        state=state,
        last_published=last_published,
        previous_error=previous_error,
    )


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
                "Queued ZMQ publisher. Payload inputs are validated "
                "and queued. Publications are triggered exclusively "
                "through action={'action': 'publish'}."
            ),
        )
    )


__all__ = [
    "ZMQ_OUT_INPUT_PORTS",
    "ZMQ_OUT_OUTPUT_PORTS",
    "register_zmq_out_unit",
]
