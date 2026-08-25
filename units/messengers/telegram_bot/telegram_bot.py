"""TelegramBot unit: interact with an external telegram service via zmq messaging bus publish job/subscribe for the response.

Receives commands on the "data" input port.

Inputs (dict):
tg_start: {"action": "tg_start"}
tg_stop: {"action": "tg_stop"}
get_unread: {"action": "get_unread", "messenger": "telegram"}
send_message: {"action": "send_message", "messenger": "telegram", "chat_id": <int_or_str>, "message": "<text>"}
raw: any payload dict from supported Telegram Bot API methods

Outputs:

update: {"type":"update","update": } on success
status: {"type":"status","status":"..."} for start/stop/other statuses
error: {"type":"error","error":"..."} on failure

Params (must be provided in params dict):

- bot_token (str)
- wait_for_delivery (bool, default true) — whether to wait for tg message delivery
- delivery_timeout_s (int, default 60) — max seconds to wait when wait_for_delivery is true
- mark_read (bool, default true) — mark inbox read up to highest fetched message on get_unread
- zmq_sub_endpoint (str) - e.g. tcp://127.0.0.1:5557 Telegram bot poller's subscription endpoint for the jobs to publish,
- update_endpoint, (str) - e.g. tcp://127.0.0.1:5556 Telegram bot poller's updates channel (fans out tg updates),
- response_endpoint (str) - e.g. tcp://127.0.0.1:5558 The unit's endpoint to receive responses from Telegram bot poller,
- workflow_path (str)  - e.g. tool.send_message.workflow

"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
import uuid
from typing import Any

from runtime.executor import GraphWakeupCallback, GraphWakeupEvent
from services.logging import setup_colored_logging
from services.zmq import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig
from units.registry import UnitSpec, register_unit

logger = setup_colored_logging(logging.DEBUG)

TELEGRAM_BOT_INPUT_PORTS = [
    ("tg_start", "Any"),
    ("tg_stop", "Any"),
    ("get_unread", "Any"),
    ("send_message", "Any"),
    ("raw", "Any"),
]

TELEGRAM_BOT_OUTPUT_PORTS = [
    ("update", "Any"),
    ("status", "Any"),
    ("error", "Any"),
]

MESSENGER = "telegram"

# Runtime-only resources. These must not be placed in serialized state.
_TELEGRAM_LISTENER_TASKS: dict[str, asyncio.Task[Any]] = {}
_TELEGRAM_LISTENER_STOPS: dict[str, asyncio.Event] = {}
_TELEGRAM_SUBSCRIBERS: dict[str, ZmqSubscriber] = {}
_TELEGRAM_UPDATE_SUBSCRIBERS: dict[str, ZmqSubscriber] = {}

# unit_id -> run_id -> future
_TELEGRAM_PENDING: dict[
    str,
    dict[str, asyncio.Future[dict[str, Any]]],
] = {}


def _param_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }

    return default


def _int_param(
    value: Any,
    *,
    default: int,
    minimum: int = 1,
    maximum: int = 1000,
) -> int:
    try:
        number = int(value if value is not None else default)
    except (TypeError, ValueError):
        number = default

    return max(minimum, min(number, maximum))


def _topic_name(topic: Any) -> str:
    if isinstance(topic, (bytes, bytearray)):
        return topic.decode(errors="replace")

    return str(topic)


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
            "TelegramBot requires params['_executor'], params['_executor_loop'], or params['_background_loop']"
        )

    if not loop.is_running():
        raise RuntimeError(
            "TelegramBot background event loop is not running"
        )

    return loop


def _schedule_coroutine(
    coroutine: Any,
    loop: asyncio.AbstractEventLoop,
) -> concurrent.futures.Future[Any]:
    future = asyncio.run_coroutine_threadsafe(coroutine, loop)

    def _done(done_future: Any) -> None:
        try:
            done_future.result()
        except asyncio.CancelledError:
            logger.debug(
                "TelegramBot background operation cancelled"
            )
        except Exception:
            logger.exception(
                "TelegramBot background operation failed"
            )

    future.add_done_callback(_done)
    return future


def _result_from_result_topic(
    payload: dict[str, Any],
) -> dict[str, Any]:
    status = payload.get("status") or payload.get("payload_status")
    response = payload.get("response")

    if status not in (None, "ok", True):
        return {
            "type": "error",
            "error": payload.get("error") or response,
        }

    if isinstance(response, dict):
        unread = response.get("unread")

        if (
            isinstance(unread, dict)
            and unread.get("type") == "update"
            and "update" in unread
        ):
            return {
                "type": "update",
                "update": unread.get("update"),
            }

        if (
            isinstance(unread, dict)
            and "chats" in unread
            and "last_read" in unread
        ):
            return {
                "type": "update",
                "messenger": MESSENGER,
                "update": unread,
            }

        if (
            response.get("type") == "update"
            and "update" in response
        ):
            return {
                "type": "update",
                "update": response.get("update"),
            }

    return {
        "type": "update",
        "update": response,
    }


def _emit_get_unread_wakeup(
    *,
    unit_id: str,
    callback: GraphWakeupCallback | None,
) -> None:
    if callback is None:
        return

    callback(
        GraphWakeupEvent(
            unit_id=unit_id,
            payload={
                "get_unread": {
                    "action": "get_unread",
                    "messenger": "telegram",
                },
            },
            seq=time.time_ns(),
        )
    )


async def _response_listener(
    *,
    unit_id: str,
    response_endpoint: str,
    stop_event: asyncio.Event,
    ready_event: asyncio.Event,
) -> None:
    subscriber = ZmqSubscriber(
        config=ZmqSubscriptionConfig(
            sub_endpoint=response_endpoint,
            topics=["result", "error"],
        ),
        loop=asyncio.get_running_loop(),
    )

    _TELEGRAM_SUBSCRIBERS[unit_id] = subscriber
    _ = _TELEGRAM_PENDING.setdefault(unit_id, {})

    async def _handler(topic: Any, payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        topic_name = _topic_name(topic)

        if topic_name not in {"result", "error"}:
            return

        run_id = payload.get("run_id")
        if run_id is None:
            logger.debug(
                "TelegramBot ignoring response without run_id: %r",
                payload,
            )
            return

        pending = _TELEGRAM_PENDING.get(unit_id, {})
        future = pending.get(str(run_id))

        if future is None or future.done():
            logger.warning(
                "TelegramBot ignoring response for unknown run_id=%s",
                run_id,
            )
            return

        if topic_name == "error":
            future.set_result(
                {
                    "type": "error",
                    "error": payload.get("error")
                    or payload.get("response"),
                }
            )
            return

        future.set_result(
            _result_from_result_topic(payload)
        )

    subscriber.on_any(_handler)
    await subscriber.start()
    ready_event.set()

    # logger.debug(
    #    "TelegramBot response listener started: unit=%s endpoint=%s",
    #    unit_id,
    #    response_endpoint,
    # )

    try:
        _ = await stop_event.wait()
    finally:
        try:
            await subscriber.stop()
        except (TypeError, RuntimeError, TimeoutError):
            pass

        _ = _TELEGRAM_SUBSCRIBERS.pop(unit_id, None)


async def _update_listener(
    *,
    unit_id: str,
    update_endpoint: str,
    callback: GraphWakeupCallback | None,
    stop_event: asyncio.Event,
    ready_event: asyncio.Event,
) -> None:
    subscriber = ZmqSubscriber(
        config=ZmqSubscriptionConfig(
            sub_endpoint=update_endpoint,
            topics=["update_batch"],
        ),
        loop=asyncio.get_running_loop(),
    )

    _TELEGRAM_UPDATE_SUBSCRIBERS[unit_id] = subscriber

    async def _handler(topic: Any, payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        if _topic_name(topic) != "update_batch":
            return

        logger.debug(
            "TelegramBot received update_batch: unit=%s update=%r",
            unit_id,
            payload.get("update"),
        )

        _emit_get_unread_wakeup(
            unit_id=unit_id,
            callback=callback,
        )

    subscriber.on_any(_handler)
    await subscriber.start()
    ready_event.set()

    # logger.debug(
    #    "TelegramBot update listener started: unit=%s endpoint=%s",
    #    unit_id,
    #    update_endpoint,
    # )

    try:
        _ = await stop_event.wait()
    finally:
        try:
            await subscriber.stop()
        except (TypeError, RuntimeError, TimeoutError):
            pass

        _ = _TELEGRAM_UPDATE_SUBSCRIBERS.pop(unit_id, None)


async def _run_telegram_listeners(
    *,
    unit_id: str,
    response_endpoint: str,
    update_endpoint: str,
    callback: GraphWakeupCallback | None,
    stop_event: asyncio.Event,
    ready_event: asyncio.Event,
) -> None:
    response_ready = asyncio.Event()
    update_ready = asyncio.Event()

    response_task = asyncio.create_task(
        _response_listener(
            unit_id=unit_id,
            response_endpoint=response_endpoint,
            stop_event=stop_event,
            ready_event=response_ready,
        ),
        name=f"TelegramBotResponseListener:{unit_id}",
    )

    update_task = asyncio.create_task(
        _update_listener(
            unit_id=unit_id,
            update_endpoint=update_endpoint,
            callback=callback,
            stop_event=stop_event,
            ready_event=update_ready,
        ),
        name=f"TelegramBotUpdateListener:{unit_id}",
    )

    try:
        _ = await asyncio.gather(
            response_ready.wait(),
            update_ready.wait(),
        )
        ready_event.set()

        _ = await stop_event.wait()
    finally:
        _ = response_task.cancel()
        _ = update_task.cancel()

        _ = await asyncio.gather(
            response_task,
            update_task,
            return_exceptions=True,
        )


async def _start_telegram_listeners(
    *,
    unit_id: str,
    response_endpoint: str,
    update_endpoint: str,
    callback: GraphWakeupCallback | None,
) -> None:
    if unit_id in _TELEGRAM_LISTENER_TASKS:
        return

    stop_event = asyncio.Event()
    ready_event = asyncio.Event()

    task = asyncio.create_task(
        _run_telegram_listeners(
            unit_id=unit_id,
            response_endpoint=response_endpoint,
            update_endpoint=update_endpoint,
            callback=callback,
            stop_event=stop_event,
            ready_event=ready_event,
        ),
        name=f"TelegramBotListeners:{unit_id}",
    )

    _TELEGRAM_LISTENER_STOPS[unit_id] = stop_event
    _TELEGRAM_LISTENER_TASKS[unit_id] = task

    try:
        _ = await asyncio.wait_for(
            ready_event.wait(),
            timeout=5,
        )
    except Exception:
        stop_event.set()
        _ = task.cancel()
        _ = await asyncio.gather(task, return_exceptions=True)

        _ = _TELEGRAM_LISTENER_STOPS.pop(unit_id, None)
        _ = _TELEGRAM_LISTENER_TASKS.pop(unit_id, None)
        raise


async def _stop_telegram_listeners(unit_id: str) -> None:
    stop_event = _TELEGRAM_LISTENER_STOPS.pop(unit_id, None)
    task = _TELEGRAM_LISTENER_TASKS.pop(unit_id, None)

    if stop_event is not None:
        stop_event.set()

    if task is not None and task is not asyncio.current_task():
        try:
            await task
        except asyncio.CancelledError:
            pass

    _ = _TELEGRAM_SUBSCRIBERS.pop(unit_id, None)
    _ = _TELEGRAM_UPDATE_SUBSCRIBERS.pop(unit_id, None)

    pending = _TELEGRAM_PENDING.pop(unit_id, {})

    for future in pending.values():
        if not future.done():
            _ = future.cancel()


async def _wait_for_response(
    *,
    unit_id: str,
    run_id: str,
    timeout_s: int,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()

    pending = _TELEGRAM_PENDING.setdefault(unit_id, {})
    pending[str(run_id)] = future

    try:
        return await asyncio.wait_for(
            future,
            timeout=timeout_s,
        )
    finally:
        _ = pending.pop(str(run_id), None)


def _publish_job_zmq_only(
    params: dict[str, Any],
    *,
    act: str,
    action_payload: Any,
) -> dict[str, Any]:
    unit_id = params.get("_unit_id")
    workflow_path = params.get("workflow_path")
    zmq_pub_endpoint = params.get("zmq_sub_endpoint")
    response_endpoint = params.get("response_endpoint")
    update_endpoint = params.get("update_endpoint")

    callback: GraphWakeupCallback | None = params.get(
        "_graph_wakeup_callback"
    )

    if not isinstance(unit_id, str) or not unit_id:
        return {
            "type": "error",
            "error": "Missing required param: _unit_id",
        }

    missing = [
        name
        for name, value in (
            ("workflow_path", workflow_path),
            ("zmq_sub_endpoint", zmq_pub_endpoint),
            ("response_endpoint", response_endpoint),
            ("update_endpoint", update_endpoint),
        )
        if not value
    ]

    if missing:
        return {
            "type": "error",
            "error": (
                "Missing required params: "
                + ", ".join(missing)
            ),
        }

    loop = _get_background_loop(params)

    if act == "tg_stop":
        try:
            _schedule_coroutine(
                _stop_telegram_listeners(unit_id),
                loop,
            ).result(timeout=5)
        except Exception as exc:
            return {
                "type": "error",
                "error": str(exc) or type(exc).__name__,
            }

        return {
            "type": "status",
            "status": "stopped",
        }

    raw: dict[str, Any] = {"action": act}

    if isinstance(action_payload, dict):
        raw.update(action_payload)

    if act == "get_unread":
        raw.setdefault(
            "mark_read",
            _param_bool(
                params.get("mark_read"),
                default=True,
            ),
        )
        raw.setdefault(
            "wait_for_delivery",
            _param_bool(
                params.get("wait_for_delivery"),
                default=True,
            ),
        )

    if act == "send_message":
        raw.setdefault(
            "wait_for_delivery",
            _param_bool(
                params.get("wait_for_delivery"),
                default=True,
            ),
        )

    run_id = str(params.get("run_id") or uuid.uuid4())

    timeout_s = _int_param(
        params.get("delivery_timeout_s"),
        default=60,
        minimum=1,
        maximum=3600,
    )

    unit_param_overrides = params.get("unit_param_overrides")
    format_ = params.get("format")

    def _thread_main() -> dict[str, Any]:
        if not isinstance(response_endpoint, str) or not response_endpoint:
            raise ValueError("response_endpoint must be a non-empty string")

        if not isinstance(update_endpoint, str) or not update_endpoint:
            raise ValueError("update_endpoint must be a non-empty string")

        if not isinstance(zmq_pub_endpoint, str) or not zmq_pub_endpoint:
            raise ValueError("zmq_pub_endpoint must be a non-empty string")

        # Start both persistent subscribers before publishing the job.
        _schedule_coroutine(
            _start_telegram_listeners(
                unit_id=unit_id,
                response_endpoint=response_endpoint,
                update_endpoint=update_endpoint,
                callback=callback,
            ),
            loop,
        ).result(timeout=6)

        # Register the pending response before publishing, so a fast result
        # cannot be missed.
        wait_future = asyncio.run_coroutine_threadsafe(
            _wait_for_response(
                unit_id=unit_id,
                run_id=run_id,
                timeout_s=timeout_s,
            ),
            loop,
        )

        ZmqPublisher(
            pub_endpoint=zmq_pub_endpoint,
        ).publish_job(
            run_id=run_id,
            workflow_path=workflow_path,
            initial_inputs={
                "raw": raw,
            },
            unit_param_overrides=unit_param_overrides,
            format=format_,
            response_endpoint=response_endpoint,
            update_endpoint=update_endpoint,
        )

        try:
            return wait_future.result(timeout=timeout_s + 1)
        except concurrent.futures.TimeoutError:
            _ = wait_future.cancel()
            return {
                "type": "error",
                "error": (
                    f"operation timed out after {timeout_s}s"
                ),
            }

    result_future: concurrent.futures.Future[
        dict[str, Any]
    ] = concurrent.futures.Future()

    def _run() -> None:
        try:
            result_future.set_result(_thread_main())
        except Exception as exc:
            result_future.set_result(
                {
                    "type": "error",
                    "error": str(exc) or type(exc).__name__,
                }
            )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    _ = executor.submit(_run)

    try:
        return result_future.result(timeout=timeout_s + 7)
    except concurrent.futures.TimeoutError:
        return {
            "type": "error",
            "error": (
                f"operation timed out after {timeout_s}s"
            ),
        }
    finally:
        executor.shutdown(
            wait=False,
            cancel_futures=True,
        )


def _ptb_unit_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    del dt

    if state is None:
        state = {}

    action_payload: Any = None
    action_name: str | None = None

    for port_name in (
        "tg_start",
        "tg_stop",
        "get_unread",
        "send_message",
        "raw",
    ):
        if (
            port_name in inputs
            and inputs[port_name] is not None
        ):
            value = inputs[port_name]

            if isinstance(value, dict):
                action_payload = dict(value)
            else:
                action_payload = (
                    {"action": port_name}
                    if value
                    else None
                )

            action_name = port_name
            break

    if action_payload is None and action_name is None:
        return (
            {
                "update": None,
                "status": None,
                "error": {
                    "type": "error",
                    "error": "No action input provided",
                },
            },
            state,
        )

    action = (
        action_payload.get("action")
        if (
            isinstance(action_payload, dict)
            and "action" in action_payload
        )
        else action_name
    )

    try:
        result = _publish_job_zmq_only(
            params,
            act=str(action) if action is not None else "",
            action_payload=action_payload,
        )
    except (TypeError, ValueError, RuntimeError) as exc:
        return (
            {
                "update": None,
                "status": None,
                "error": {
                    "type": "error",
                    "error": str(exc) or type(exc).__name__,
                },
            },
            state,
        )

    if not isinstance(result, dict):
        result = {
            "type": "update",
            "update": result,
        }

    result_type = result.get("type")

    if result_type == "update":
        return (
            {
                "update": result,
                "status": None,
                "error": None,
            },
            state,
        )

    if result_type == "status":
        return (
            {
                "update": None,
                "status": result,
                "error": None,
            },
            state,
        )

    if result_type == "error":
        return (
            {
                "update": None,
                "status": None,
                "error": result,
            },
            state,
        )

    return (
        {
            "update": result,
            "status": None,
            "error": None,
        },
        state,
    )


def register_ptb_telegram_bot() -> None:
    register_unit(
        UnitSpec(
            type_name="TelegramBot",
            input_ports=TELEGRAM_BOT_INPUT_PORTS,
            output_ports=TELEGRAM_BOT_OUTPUT_PORTS,
            step_fn=_ptb_unit_step,
            environment_tags=["messengers"],
            environment_tags_are_agnostic=False,
            supports_graph_wakeup=True,
            description=(
                "Telegram bot wrapper using persistent ZMQ subscribers. "
                "The response endpoint receives result and error topics. "
                "The update endpoint receives update_batch topics. "
                "The listeners remain active until tg_stop."
            ),
        )
    )
