"""TelegramBot unit: interact with an external telegram service via zmq messaging bus publish job/subscribe for the response.

Receives commands on the "data" input port.

Inputs (dict):
tg_start: {"action": "tg_start"}
tg_stop: {"action": "tg_stop"}
get_unread: {"action": "get_unread", "messenger": "telegram", "account": "<bot>"}
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
import uuid
from typing import Any, Dict, Optional, Tuple

from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig
from units.registry import UnitSpec, register_unit

logger = logging.getLogger(__name__)

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


def _param_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def _int_param(
    value: Any, *, default: int, minimum: int = 1, maximum: int = 1000
) -> int:
    try:
        n = int(value if value is not None else default)
    except (TypeError, ValueError):
        n = default
    return max(minimum, min(n, maximum))


async def _wait_for_job_response(
    *,
    subscriber: ZmqSubscriber,
    run_id: str,
    timeout_s: int,
) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[Dict[str, Any]] = loop.create_future()

    rid_str = str(run_id)

    def _maybe_set(topic: Any, payload: Any) -> None:
        if fut.done():
            return
        if not isinstance(payload, dict):
            return

        received_rid = payload.get("run_id")
        if received_rid is None or str(received_rid) != rid_str:
            logger.debug(
                "TelegramBot: ignoring zmq response due to run_id mismatch "
                "(expected=%s received=%r topic=%r payload_keys=%s)",
                rid_str,
                received_rid,
                topic,
                list(payload.keys()),
            )
            return

        t = topic.decode() if isinstance(topic, (bytes, bytearray)) else str(topic)

        if t == "result":
            status = payload.get("status") or payload.get("payload_status")
            response = payload.get("response")

            if status in (None, "ok", True):
                if isinstance(response, dict) and "unread" in response:
                    unread = response.get("unread")
                    if (
                        isinstance(unread, dict)
                        and unread.get("type") == "update"
                        and "update" in unread
                    ):
                        fut.set_result(
                            {"type": "update", "update": unread.get("update")}
                        )
                        return
                    if (
                        isinstance(unread, dict)
                        and "chats" in unread
                        and "last_read" in unread
                    ):
                        fut.set_result({"type": "update", "update": unread})
                        return

                if (
                    isinstance(response, dict)
                    and response.get("type") == "update"
                    and "update" in response
                ):
                    fut.set_result({"type": "update", "update": response.get("update")})
                else:
                    fut.set_result({"type": "update", "update": response})
            else:
                fut.set_result(
                    {
                        "type": "error",
                        "error": payload.get("error") or payload.get("response"),
                    }
                )

    async def _handler(topic: Any, payload: Any) -> None:
        _maybe_set(topic, payload)

    subscriber.on_any(_handler)
    try:
        return await asyncio.wait_for(fut, timeout=timeout_s)
    finally:
        try:
            await subscriber.stop()
        except Exception:
            pass


def _publish_job_zmq_only(
    params: Dict[str, Any],
    *,
    act: str,
    action_payload: Any,
) -> Dict[str, Any]:
    run_id = params.get("run_id") or str(uuid.uuid4())
    workflow_path = params.get("workflow_path")  # mandatory
    zmq_pub_endpoint = params.get("zmq_sub_endpoint")  # (kept from original code)
    response_endpoint = params.get("response_endpoint")

    unit_param_overrides = params.get("unit_param_overrides")
    format_ = params.get("format")

    if not workflow_path or not zmq_pub_endpoint:
        return {
            "type": "error",
            "error": "Missing required params for ZMQ path: workflow_path and zmq_sub_endpoint",
        }

    raw: Dict[str, Any] = {"action": act}
    if isinstance(action_payload, dict):
        raw.update(action_payload)

    if act == "get_unread":
        raw.setdefault("mark_read", _param_bool(params.get("mark_read"), default=True))
        raw.setdefault(
            "wait_for_delivery",
            _param_bool(params.get("wait_for_delivery"), default=True),
        )
    if act == "send_message":
        raw.setdefault(
            "wait_for_delivery",
            _param_bool(params.get("wait_for_delivery"), default=True),
        )

    initial_inputs = {"raw": raw}

    # no-wait mode
    if not response_endpoint:
        ZmqPublisher(pub_endpoint=zmq_pub_endpoint).publish_job(
            run_id=run_id,
            workflow_path=workflow_path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=format_,
            response_endpoint=response_endpoint,
            update_endpoint=params.get("update_endpoint"),
        )
        return {"type": "status", "status": "published_via_zmq"}

    timeout = _int_param(
        params.get("delivery_timeout_s"), default=60, minimum=1, maximum=3600
    )

    def _thread_main() -> Dict[str, Any]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _run() -> Dict[str, Any]:
            sub_cfg = ZmqSubscriptionConfig(
                sub_endpoint=response_endpoint,
                topics=["result", "error"],
            )
            subscriber = ZmqSubscriber(config=sub_cfg, loop=loop)
            await subscriber.start()

            wait_task = asyncio.create_task(
                _wait_for_job_response(
                    subscriber=subscriber,
                    run_id=run_id,
                    timeout_s=timeout,
                )
            )

            def _pub() -> None:
                ZmqPublisher(pub_endpoint=zmq_pub_endpoint).publish_job(
                    run_id=run_id,
                    workflow_path=workflow_path,
                    initial_inputs=initial_inputs,
                    unit_param_overrides=unit_param_overrides,
                    format=format_,
                    response_endpoint=response_endpoint,
                    update_endpoint=params.get("update_endpoint"),
                )

            await asyncio.to_thread(_pub)
            return await wait_task

        try:
            return loop.run_until_complete(_run())
        finally:
            try:
                loop.stop()
                loop.close()
            except Exception:
                pass

    # preserve original behavior: run in a thread and wait with a timeout
    result_q: concurrent.futures.Future[Dict[str, Any]] = concurrent.futures.Future()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as t:
        t.submit(_thread_main).add_done_callback(
            lambda f: result_q.set_result(f.result())
        )
        try:
            return result_q.result(timeout=timeout + 1)
        except concurrent.futures.TimeoutError:
            return {"type": "error", "error": f"operation timed out after {timeout}s"}


def _ptb_unit_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    action_payload: Any = None
    action_name: Optional[str] = None

    # Remove "start step entirely": do not consider tg_start at all.
    for port_name in ("tg_stop", "get_unread", "send_message", "raw"):
        if port_name in inputs and inputs[port_name] is not None:
            raw_in = inputs[port_name]
            if isinstance(raw_in, dict):
                action_payload = dict(raw_in)
            else:
                action_payload = {"action": port_name} if raw_in else None
            action_name = port_name
            break

    if action_payload is None and action_name is None:
        return (
            {
                "update": None,
                "status": None,
                "error": {"type": "error", "error": "No action input provided"},
            },
            state,
        )

    act = (
        action_payload.get("action")
        if isinstance(action_payload, dict) and "action" in action_payload
        else action_name
    )

    # No poller.start() / no already_running / single path: zmq publish/response.
    try:
        result = _publish_job_zmq_only(
            params,
            act=str(act) if act is not None else "",
            action_payload=action_payload,
        )
    except Exception as exc:
        return (
            {
                "update": None,
                "status": None,
                "error": {"type": "error", "error": str(exc) or type(exc).__name__},
            },
            state,
        )

    if not isinstance(result, dict):
        result = {"type": "update", "update": result}

    rtype = result.get("type")
    if rtype == "update":
        out_update, out_status, out_error = result, None, None
    elif rtype == "status":
        out_update, out_status, out_error = None, result, None
    elif rtype == "error":
        out_update, out_status, out_error = None, None, result
    else:
        out_update, out_status, out_error = result, None, None

    return (
        {"update": out_update, "status": out_status, "error": out_error},
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
            description=(
                "Wrapper around TelegramBotPoller semantics using a ZMQ publish/response path. "
                "Operations: tg_stop, get_unread, send_message, raw. "
                "Publishes a ZMQ job and (when response_endpoint is provided) waits for topics: result,error."
            ),
        )
    )
