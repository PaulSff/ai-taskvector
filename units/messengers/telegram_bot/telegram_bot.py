from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from messengers_integrations import TelegramBotPoller
from runtime import (
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
)
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


def _build_poller(params: Dict[str, Any]) -> TelegramBotPoller:
    bot_token = params.get("bot_token") or params.get("account")
    if not bot_token:
        raise ValueError("bot_token param required for TelegramBot unit")
    return TelegramBotPoller(params)


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
            # Helps catch subscription/topic mismatch or wrong correlation id
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
            fut.set_result({"type": "update", "update": payload.get("outputs")})
        elif t == "error":
            fut.set_result({"type": "error", "error": payload.get("error")})

    seen = 0

    async def _handler(topic: Any, payload: Any) -> None:
        nonlocal seen
        if seen < 10:
            logger.info(
                "TelegramBot: received zmq message topic=%r payload_type=%s payload_keys=%s",
                topic,
                type(payload).__name__,
                list(payload.keys()) if isinstance(payload, dict) else None,
            )
            seen += 1
        _maybe_set(topic, payload)

    subscriber.on_any(_handler)
    try:
        return await asyncio.wait_for(fut, timeout=timeout_s)
    finally:
        try:
            await subscriber.stop()
        except Exception:
            pass


def _publish_job_when_already_running(
    params: Dict[str, Any],
    *,
    act: str,
    action_payload: Any,
) -> Dict[str, Any]:
    run_id = params.get("run_id") or str(uuid.uuid4())
    workflow_path = params.get("workflow_path")  # mandatory
    zmq_pub_endpoint = params.get("zmq_sub_endpoint")
    response_endpoint = params.get("response_endpoint")

    unit_param_overrides = params.get("unit_param_overrides")
    format_ = params.get("format")

    if not workflow_path or not zmq_pub_endpoint:
        return {
            "type": "error",
            "error": "Missing required params for ZMQ fallback: workflow_path and zmq_sub_endpoint",
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
        return {"type": "status", "status": "published_via_zmq_when_already_running"}

    timeout_param = params.get("delivery_timeout_s")
    timeout = _int_param(timeout_param, default=60, minimum=1, maximum=3600)
    logger.info(
        "TelegramBot: wait-for-response timeout param delivery_timeout_s=%r -> timeout_s=%s",
        timeout_param,
        timeout,
    )

    result_q: "concurrent.futures.Future[Dict[str, Any]]" = concurrent.futures.Future()

    def _thread_main() -> None:
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

            # publish in thread to avoid blocking this loop during send_job
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
            res = loop.run_until_complete(_run())
            result_q.set_result(res)
        except Exception as e:
            result_q.set_result({"type": "error", "error": str(e) or type(e).__name__})
        finally:
            try:
                loop.stop()
                loop.close()
            except Exception:
                pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as t:
        t.submit(_thread_main)
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

    for port_name in ("tg_start", "tg_stop", "get_unread", "send_message", "raw"):
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

    try:
        poller = state.get("poller")
        if poller is None:
            poller = _build_poller(params)
            state["poller"] = poller
    except Exception as exc:
        return (
            {
                "update": None,
                "status": None,
                "error": {"type": "error", "error": str(exc) or type(exc).__name__},
            },
            state,
        )

    async def _dispatch() -> Dict[str, Any]:
        start_res = await poller.start()

        if (
            isinstance(start_res, dict)
            and start_res.get("type") == "status"
            and start_res.get("status") == "already_running"
        ):
            return _publish_job_when_already_running(
                params,
                act=str(act) if act is not None else "",
                action_payload=action_payload,
            )

        if act == "tg_start":
            return start_res

        if act == "tg_stop":
            return await poller.stop(force=True)

        if act == "get_unread":
            poller.params["mark_read"] = _param_bool(
                params.get("mark_read"), default=True
            )
            return await poller.get_unread()

        if act == "send_message":
            if not isinstance(action_payload, dict):
                raise ValueError("send_message payload must be a dict")
            chat_id = action_payload.get("chat_id")
            message = action_payload.get("message")
            if chat_id is None or message is None:
                raise ValueError("send_message requires chat_id and message")

            wait_for_delivery = action_payload.get(
                "wait_for_delivery", params.get("wait_for_delivery")
            )
            return await poller.send_message(
                chat_id=chat_id,
                message=message,
                wait_for_delivery=wait_for_delivery,
            )

        if act == "raw":
            if not isinstance(action_payload, dict):
                raise ValueError("raw payload must be a dict")
            method = action_payload.get("method")
            raw_params = action_payload.get("params")
            if not isinstance(method, str):
                raise ValueError("raw requires method (str)")
            return await poller.raw(method=method, params=raw_params)

        return {"type": "error", "error": f"Unhandled action: {act}"}

    async def _run_in_loop() -> Dict[str, Any]:
        return await _dispatch()

    timeout = _int_param(
        params.get("delivery_timeout_s"), default=60, minimum=1, maximum=3600
    )

    try:
        bg_loop = params.get("_background_loop") or params.get("_executor_loop")
        if isinstance(bg_loop, asyncio.AbstractEventLoop):
            if not bg_loop.is_running():
                raise RuntimeError("background loop not running")
            fut = asyncio.run_coroutine_threadsafe(_run_in_loop(), bg_loop)
            try:
                result = fut.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                try:
                    fut.cancel()
                except Exception:
                    pass
                return (
                    {
                        "update": None,
                        "status": None,
                        "error": {
                            "type": "error",
                            "error": f"operation timed out after {timeout}s",
                        },
                    },
                    state,
                )
        else:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError(
                    "This unit requires _background_loop when called from an already-running event loop."
                )
            result = loop.run_until_complete(_run_in_loop())
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
                "Wrapper around TelegramBotPoller (no local polling). "
                "Operations: tg_start, tg_stop, get_unread, send_message, raw. "
                "If poller.start() reports already_running, publishes a ZMQ job instead "
                "and waits for a response on response_endpoint (topics: result,error), "
                "then shuts down safely."
            ),
        )
    )
