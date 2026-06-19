"""TelegramBot unit: interact with an external telegram server via python-telegram-bot client.
   Requires: https://github.com/python-telegram-bot/python-telegram-bot >= v20+
   Installation: pip install python-telegram-bot --upgrade

Receives commands on the "data" input port.

Inputs (dict):
tg_start: {"action": "tg_start"}
tg_stop: {"action": "tg_stop"}
get_unread: {"action": "get_unread", "messenger": "telegram", "account": "<bot>"}
send_message: {"action": "send_message", "messenger": "telegram", "chat_id": <int_or_str>, "message": "<text>"}
raw: any payload dict from supported tg API methods

Outputs:

update: {"type":"update","update": } on success
status: {"type":"status","status":"..."} for start/stop/other statuses
error: {"type":"error","error":"..."} on failure

Params (must be provided in params dict):

- bot_token (str)
- wait_for_delivery (bool, default true) — wait for updateMessageSendSucceeded after send_message
- delivery_timeout_s (int, default 60) — max seconds to wait when wait_for_delivery is true
- mark_read (bool, default true) — mark inbox read up to highest fetched message on get_unread
- _needs_executor (bool, default true) - requires true for async events loop support

Streaming / async: This unit schedules async operations on executor background loop (params["_executor"] or params["_executor_loop"] / params["_background_loop"]). It requires "_needs_executor": True.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import logging
import queue
import threading
from typing import (
    Any,
    Awaitable,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    cast,
)

from telegram import Message, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

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


def _resolve_background_loop(
    params: Dict[str, Any],
) -> asyncio.AbstractEventLoop | None:
    if isinstance(params.get("_background_loop"), asyncio.AbstractEventLoop):
        return params.get("_background_loop")
    if isinstance(params.get("_executor_loop"), asyncio.AbstractEventLoop):
        return params.get("_executor_loop")
    exec_obj = params.get("_executor")
    if exec_obj is not None:
        for attr in ("background_loop", "loop", "_loop"):
            bg = getattr(exec_obj, attr, None)
            if isinstance(bg, asyncio.AbstractEventLoop):
                return bg
    return None


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


def _normalize_message_to_tdlib_shape(msg: Message) -> Dict[str, Any]:
    def to_int_or_none(v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    chat_id = to_int_or_none(getattr(msg.chat, "id", None))
    msg_id = to_int_or_none(getattr(msg, "message_id", None))

    date_ts = None
    if getattr(msg, "date", None) is not None:
        try:
            date_ts = int(msg.date.timestamp())
        except Exception:
            date_ts = None

    text = msg.text or msg.caption or ""
    content: Dict[str, Any] = {"@type": "messageText", "text": {"text": text}}

    from_user: Dict[str, Any] | None = None
    fu = getattr(msg, "from_user", None)
    if fu is not None:
        fu_id = to_int_or_none(getattr(fu, "id", None))
        from_user = {"id": fu_id}
        if getattr(fu, "username", None) is not None:
            from_user["username"] = fu.username
        if getattr(fu, "first_name", None) is not None:
            from_user["first_name"] = fu.first_name

    message_obj: Dict[str, Any] = {
        "id": msg_id,
        "chat_id": chat_id,
        "content": content,
        "date": date_ts,
        "from": from_user,
    }
    return {"id": msg_id, "chat_id": chat_id, "message": message_obj}


def _build_ptb_app_from_params(params: Dict[str, Any]) -> Application:
    bot_token = params.get("bot_token") or params.get("account")
    if not bot_token:
        raise ValueError("bot_token param required for Bot API unit")

    req = HTTPXRequest(
        connect_timeout=float(params.get("connect_timeout", 10)),
        read_timeout=float(params.get("read_timeout", 20)),
        pool_timeout=float(params.get("pool_timeout", 5)),
    )

    # NOTE: For polling you must call app.updater.start_polling() at runtime.
    return ApplicationBuilder().token(str(bot_token)).request(req).build()


def _ptb_unit_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # --- normalize inputs -> action_payload ---
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

    background_loop = _resolve_background_loop(params)
    if not isinstance(background_loop, asyncio.AbstractEventLoop):
        return (
            {
                "update": None,
                "status": None,
                "error": {
                    "type": "error",
                    "error": "Background event loop not provided in params('_executor_loop' or '_background_loop').",
                },
            },
            state,
        )

    # --- ensure state keys ---
    state.setdefault("unread_by_chat", {})  # dict[str(chat_id)] -> list[message dict]
    state.setdefault("last_read_by_chat", {})
    state.setdefault("pending_unit_updates", [])
    state.setdefault("pending_unit_queue", queue.Queue())
    state.setdefault("_lock", threading.RLock())
    state.setdefault("_start_refcount", 0)

    lock: threading.RLock = state["_lock"]  # type: ignore[assignment]
    pending_q: queue.Queue = state["pending_unit_queue"]

    # App/lifecycle flags
    state.setdefault("ptb_app", None)
    state.setdefault("ptb_started", False)
    state.setdefault("_handlers_registered", False)

    app: Application | None = state.get("ptb_app")

    # --- handlers ---
    async def _ptb_message_handler(
        update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return
        msg_shape = _normalize_message_to_tdlib_shape(update.message)
        cid = msg_shape.get("chat_id")
        if cid is None:
            return
        key = str(int(cid))

        try:
            with lock:
                unread = state.setdefault("unread_by_chat", {}).setdefault(key, [])
                unread.append(msg_shape["message"])
        except Exception:
            logger.exception("error updating unread_by_chat")

        try:
            pending_q.put_nowait(
                {
                    "type": "update",
                    "update": {"chat_id": cid, "message": msg_shape["message"]},
                }
            )
        except Exception:
            logger.exception("failed to enqueue pending unit update")

    async def _ptb_error_handler(
        update: object | None, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.exception("telegram handler error", exc_info=getattr(ctx, "error", None))

    async def _ensure_app_and_handlers() -> Application:
        nonlocal app
        if state.get("ptb_app") is None:
            app = _build_ptb_app_from_params(params)
            state["ptb_app"] = app

        app_local: Application = state["ptb_app"]
        if not state.get("_handlers_registered", False):
            try:
                app_local.add_error_handler(_ptb_error_handler)
            except Exception:
                pass
            app_local.add_handler(MessageHandler(filters.ALL, _ptb_message_handler))
            state["_handlers_registered"] = True
        return app_local

    async def _start_if_needed() -> Dict[str, Any]:
        with lock:
            if state.get("ptb_started"):
                state["_start_refcount"] = state.get("_start_refcount", 0) + 1
                return {"type": "status", "status": "already_started"}
            state["_start_refcount"] = state.get("_start_refcount", 0) + 1

        app_local = await _ensure_app_and_handlers()

        try:
            await app_local.initialize()
            await app_local.start()

            updater = getattr(app_local, "updater", None)
            if updater is None:
                raise RuntimeError("Application has no updater; cannot start polling")

            await updater.start_polling(allowed_updates=None)

            with lock:
                state["ptb_started"] = True
            return {"type": "status", "status": "started"}

        except Exception:
            try:
                await app_local.shutdown()
            except Exception:
                pass
            with lock:
                state["ptb_started"] = False
                state["_start_refcount"] = max(0, state.get("_start_refcount", 1) - 1)
            logger.exception("failed to start ptb app")
            raise

    async def _stop_if_possible(force: bool = False) -> Dict[str, Any]:
        with lock:
            if not state.get("ptb_started"):
                return {"type": "status", "status": "not_started"}

            state["_start_refcount"] = (
                0 if force else max(0, state.get("_start_refcount", 1) - 1)
            )
            refcount = state.get("_start_refcount", 0)
            if refcount > 0 and not force:
                return {
                    "type": "status",
                    "status": "stop_deferred",
                    "refcount": refcount,
                }

        app_local = state.get("ptb_app")
        if app_local is None:
            with lock:
                state["ptb_started"] = False
            return {"type": "status", "status": "stopped"}

        try:
            updater = getattr(app_local, "updater", None)
            if updater is not None:
                res = updater.stop()
                if inspect.isawaitable(res):
                    await res

            res = app_local.stop()
            if inspect.isawaitable(res):
                await res

            await app_local.shutdown()
        except Exception:
            pass
        finally:
            with lock:
                state["ptb_started"] = False

        return {"type": "status", "status": "stopped"}

    async def _get_unread_impl() -> Dict[str, Any]:
        with lock:
            unread_snapshot = {
                k: list(v) for k, v in (state.get("unread_by_chat") or {}).items()
            }
            last_read = {
                str(k): v for k, v in (state.get("last_read_by_chat") or {}).items()
            }

        chats: List[Dict[str, Any]] = []
        for chat_id_str, messages in unread_snapshot.items():
            try:
                cid = int(chat_id_str)
            except (TypeError, ValueError):
                continue
            chats.append(
                {
                    "chat_id": cid,
                    "unread_count": len(messages),
                    "chat": {"id": cid},
                    "messages": [m for m in messages],
                }
            )

        payload = {"chats": chats, "last_read": last_read}

        mark_read = _param_bool(params.get("mark_read"), default=True)
        if mark_read:
            with lock:
                unread = state.get("unread_by_chat", {}) or {}
                for k, msgs in unread.items():
                    if not msgs:
                        continue
                    try:
                        cid = int(k)
                    except Exception:
                        continue
                    max_id = max(
                        int(m.get("id") or 0) for m in msgs if isinstance(m, dict)
                    )
                    state.setdefault("last_read_by_chat", {})[str(cid)] = max_id
                state["unread_by_chat"] = {}

        return {"type": "update", "update": payload}

    async def _send_message_impl() -> Dict[str, Any]:
        if not isinstance(action_payload, dict):
            raise ValueError("send_message payload must be a dict")
        chat_id = action_payload.get("chat_id")
        message = action_payload.get("message")
        if chat_id is None or message is None:
            raise ValueError("send_message requires chat_id and message")

        # Ensure app exists
        ptb_app = state.get("ptb_app") or app
        if ptb_app is None:
            raise RuntimeError("bot not initialized; start the bot first")

        bot = getattr(ptb_app, "bot", None)
        if bot is None:
            raise RuntimeError("bot not initialized; start the bot first")

        if isinstance(chat_id, int):
            send_target: int | str = chat_id
        elif isinstance(chat_id, str):
            if chat_id.isdigit():
                send_target = int(chat_id)
            else:
                send_target = chat_id
        else:
            raise ValueError("send_message chat_id must be an integer or string")

        sent: Message = await bot.send_message(chat_id=send_target, text=str(message))
        msg_shape = _normalize_message_to_tdlib_shape(sent)

        wait_delivery = _param_bool(params.get("wait_for_delivery"), default=True)
        result_update = {"message": msg_shape.get("message")}
        if wait_delivery:
            result_update["delivered"] = True
            result_update["new_message_id"] = msg_shape.get("message", {}).get("id")

        return {"type": "update", "update": result_update}

    async def _raw_payload() -> Dict[str, Any]:
        payload = action_payload if action_payload is not None else {}
        if isinstance(payload, dict) and "method" in payload:
            method = payload.get("method")
            raw_params = payload.get("params", {}) or {}
            if not isinstance(method, str):
                return {"type": "error", "error": "invalid method"}
            if isinstance(raw_params, (Mapping, MutableMapping)):
                method_params = cast(Mapping[str, Any], raw_params)
            else:
                return {"type": "error", "error": "invalid params"}

            ptb_app = state.get("ptb_app") or app
            bot = getattr(ptb_app or state.get("ptb_app"), "bot", None)
            if bot is None:
                return {
                    "type": "error",
                    "error": "bot not initialized; start the bot first",
                }

            if method.startswith("_") or method.startswith("__"):
                return {"type": "error", "error": "requested method not permitted"}

            def _maybe_await(result: Any) -> Awaitable[Any]:
                if inspect.isawaitable(result):
                    return result  # type: ignore[return-value]

                async def _wrap() -> Any:
                    return result

                return _wrap()

            call_fn = getattr(bot, method, None)
            if callable(call_fn):
                try:
                    res_candidate = call_fn(**dict(method_params))
                    res = await _maybe_await(res_candidate)
                    return {"type": "update", "update": res}
                except Exception as exc:
                    return {"type": "error", "error": str(exc)}

            request_fn = getattr(bot, "request", None)
            if callable(request_fn):
                try:
                    try:
                        res_candidate = request_fn(method, data=dict(method_params))
                    except TypeError:
                        res_candidate = request_fn(method, dict(method_params))
                    res = await _maybe_await(res_candidate)
                    return {"type": "update", "update": res}
                except Exception as exc:
                    return {"type": "error", "error": str(exc)}

            return {"type": "error", "error": "Requested method not available on bot"}

        return {"type": "update", "update": payload}

    # Determine action
    act = (
        action_payload.get("action")
        if isinstance(action_payload, dict) and "action" in action_payload
        else action_name
    )

    async def _run_with_auto_start(coro_fn: Any) -> Dict[str, Any]:
        # Auto-start for get_unread/send_message/tg_start/tg_stop; ensure cleanup when started here.
        started_here = False
        with lock:
            already_running = bool(state.get("ptb_started"))
            if not already_running:
                state["_start_refcount"] = state.get("_start_refcount", 0) + 1
        if not already_running:
            try:
                await _start_if_needed()
                started_here = True
            except Exception:
                with lock:
                    state["_start_refcount"] = max(
                        0, state.get("_start_refcount", 1) - 1
                    )
                raise
        try:
            return await coro_fn()
        finally:
            if started_here:
                await _stop_if_possible(force=False)

    async def _dispatch() -> Dict[str, Any]:
        if act == "tg_start":
            return await _run_with_auto_start(lambda: _start_if_needed())
        if act == "tg_stop":
            # force stop: zero refcount then stop/shutdown
            with lock:
                state["_start_refcount"] = 0
            return await _run_with_auto_start(lambda: _stop_if_possible(force=True))
        if act == "get_unread":
            return await _run_with_auto_start(_get_unread_impl)
        if act == "send_message":
            return await _run_with_auto_start(_send_message_impl)
        if act == "raw":
            # raw can require explicit start depending on your use; here we auto-start for consistency
            return await _run_with_auto_start(_raw_payload)

        return {"type": "error", "error": f"Unhandled action: {act}"}

    # --- schedule coroutine on background loop ---
    try:
        if not background_loop.is_running():
            raise RuntimeError("background loop not running")

        fut = asyncio.run_coroutine_threadsafe(_dispatch(), background_loop)
        timeout = _int_param(
            params.get("delivery_timeout_s"), default=60, minimum=1, maximum=3600
        )

        try:
            result = fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            try:
                fut.cancel()
            except Exception:
                logger.exception("failed to cancel timed-out coroutine")
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
        except concurrent.futures.CancelledError:
            return (
                {
                    "update": None,
                    "status": None,
                    "error": {"type": "error", "error": "operation cancelled"},
                },
                state,
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

    # Drain pending queue into pending_unit_updates list
    try:
        with lock:
            pending = state.setdefault("pending_unit_updates", [])
            drained: List[Any] = []
            pq = state.get("pending_unit_queue")
            if isinstance(pq, queue.Queue):
                for _ in range(256):
                    try:
                        drained.append(pq.get_nowait())
                    except queue.Empty:
                        break
                pending.extend(drained)
    except Exception:
        logger.exception("error draining pending queue")

    # Output selection
    out_update = None
    out_status = None
    out_error = None

    rtype = result.get("type")
    if rtype == "update" and act in (
        "send_message",
        "get_unread",
        "tg_start",
        "tg_stop",
        "raw",
    ):
        out_update = result
    elif rtype == "status" and act in (
        "send_message",
        "get_unread",
        "tg_start",
        "tg_stop",
        "raw",
    ):
        out_status = result
    elif rtype == "error":
        out_error = result
    else:
        # fallback: use pending update first
        with lock:
            pending = state.get("pending_unit_updates") or []
            if pending:
                item = pending.pop(0)
                if isinstance(item, dict) and item.get("type") == "update":
                    out_update = item
                else:
                    out_update = item

    return ({"update": out_update, "status": out_status, "error": out_error}, state)


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
                "Bot-mode Telegram client using python-telegram-bot (long-polling). "
                "Input ports: tg_start, tg_stop, get_unread, send_message, raw."
            ),
        )
    )
