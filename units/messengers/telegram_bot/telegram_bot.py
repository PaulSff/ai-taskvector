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
    response_endpoint: Optional[str],
) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[Dict[str, Any]] = loop.create_future()

    def _maybe_set(topic: str, payload: Any) -> None:
        if fut.done():
            return
        if not isinstance(payload, dict):
            return

        rid = payload.get("run_id")
        if rid is None and isinstance(payload.get("response"), dict):
            rid = payload["response"].get("run_id")

        if rid is None or str(rid) != str(run_id):
            return

        resp = payload.get("response")

        if topic == "result":
            fut.set_result({"type": "update", "update": resp})
        elif topic == "error":
            fut.set_result({"type": "error", "error": resp})

    async def _handler(topic: str, payload: Any) -> None:
        logger.info(
            "TelegramBot: on_any fired topic=%s payload_type=%s",
            topic,
            type(payload).__name__,
        )
        _maybe_set(topic, payload)

    subscriber.on_any(_handler)
    await subscriber.start()
    logger.info(
        "TelegramBot: subscriber started at endpoint=%s run_id=%s",
        response_endpoint,
        run_id,
    )
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

    if not response_endpoint:
        ZmqPublisher(pub_endpoint=zmq_pub_endpoint).publish_job(
            run_id=run_id,
            workflow_path=workflow_path,
            initial_inputs={
                "raw": {"action": act, **(action_payload or {})}
                if isinstance(action_payload, dict)
                else {"action": act}
            },
            unit_param_overrides=unit_param_overrides,
            format=format_,
            response_endpoint=response_endpoint,
            update_endpoint=params.get("update_endpoint"),
        )
        logger.info(
            "TelegramBot: %s",
            {"type": "status", "status": "published_via_zmq_when_already_running"},
        )
        return {"type": "status", "status": "published_via_zmq_when_already_running"}

    timeout = _int_param(
        params.get("delivery_timeout_s"), default=60, minimum=1, maximum=3600
    )

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

    if act == "raw":
        pass

    initial_inputs = {"raw": raw}

    bg_loop = params.get("_background_loop")

    async def _do() -> Dict[str, Any]:
        sub_cfg = ZmqSubscriptionConfig(
            sub_endpoint=response_endpoint,
            topics=["result", "error"],
        )
        logger.info(
            "TelegramBot: creating subscriber endpoint=%s run_id=%s",
            response_endpoint,
            run_id,
        )

        subscriber = ZmqSubscriber(config=sub_cfg, loop=bg_loop)

        wait_task = asyncio.create_task(
            _wait_for_job_response(
                subscriber=subscriber,
                run_id=run_id,
                timeout_s=timeout,
                response_endpoint=response_endpoint,
            )
        )

        # Publish right after subscriber task started (subscriber is started inside wait func)
        ZmqPublisher(pub_endpoint=zmq_pub_endpoint).publish_job(
            run_id=run_id,
            workflow_path=workflow_path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=format_,
            response_endpoint=params.get("response_endpoint"),
            update_endpoint=params.get("update_endpoint"),
        )

        return await wait_task

    try:
        if isinstance(bg_loop, asyncio.AbstractEventLoop) and bg_loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(_do(), bg_loop)
            return fut.result(timeout=timeout + 1)
        return asyncio.run(_do())
    except asyncio.TimeoutError:
        return {"type": "error", "error": f"operation timed out after {timeout}s"}
    except Exception as exc:
        return {"type": "error", "error": str(exc) or type(exc).__name__}


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
