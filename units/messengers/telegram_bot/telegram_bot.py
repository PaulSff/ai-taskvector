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
from typing import Any, Awaitable, Dict, List, Mapping, MutableMapping, cast

# python-telegram-bot v20+ (asyncio) imports
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
    # Prefer explicit background loop param to avoid fragile heuristics.
    if isinstance(params.get("_background_loop"), asyncio.AbstractEventLoop):
        return params.get("_background_loop")
    if isinstance(params.get("_executor_loop"), asyncio.AbstractEventLoop):
        return params.get("_executor_loop")
    exec_obj = params.get("_executor")
    if exec_obj is not None:
        # common executor shapes: allow explicit attribute names only
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
    # coerce possible str/None ids to int|None
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


def _build_ptb_app_from_params(params):
    bot_token = params.get("bot_token") or params.get("account")
    if not bot_token:
        raise ValueError("bot_token param required for Bot API unit")

    req = HTTPXRequest(
        connect_timeout=float(params.get("connect_timeout", 10)),
        read_timeout=float(params.get("read_timeout", 20)),
        pool_timeout=float(params.get("pool_timeout", 5)),
    )

    app = ApplicationBuilder().token(str(bot_token)).request(req).build()
    return app


def _collect_chats_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    chats_out: List[Dict[str, Any]] = []
    unread_by_chat = state.setdefault("unread_by_chat", {})
    for chat_id_str, messages in unread_by_chat.items():
        try:
            cid = int(chat_id_str)
        except (TypeError, ValueError):
            continue
        normalized_msgs = []
        for m in messages:
            normalized_msgs.append(m)
        chats_out.append(
            {
                "chat_id": cid,
                "unread_count": len(normalized_msgs),
                "chat": {"id": cid},
                "messages": normalized_msgs,
            }
        )
    return chats_out


def _enqueue_error(state: Dict[str, Any], err_payload: Any) -> None:
    try:
        q = state.setdefault("pending_unit_queue", queue.Queue())
        q.put_nowait({"type": "error", "error": err_payload})
    except Exception:
        logger.exception("failed to enqueue error")


def _ptb_unit_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    # Normalize inputs -> action_payload (always dict with 'action' key)
    action_payload = None
    action_name = None
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

    # Ensure state keys and synchronization primitives
    state.setdefault("unread_by_chat", {})  # dict[str(chat_id)] -> list[message dict]
    state.setdefault("last_read_by_chat", {})
    state.setdefault("pending_unit_updates", [])
    state.setdefault("pending_unit_queue", queue.Queue())
    state.setdefault("_lock", threading.RLock())
    state.setdefault("_start_refcount", 0)
    app: Application | None = state.get("ptb_app")
    pending_q = state["pending_unit_queue"]
    lock: threading.RLock = state["_lock"]  # type: ignore[assignment]

    # Handler to receive PTB Update and store normalized message
    async def _ptb_message_handler(
        update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return
        msg_shape = _normalize_message_to_tdlib_shape(update.message)
        cid = msg_shape.get("chat_id") or (
            msg_shape["message"].get("chat_id")
            if isinstance(msg_shape.get("message"), dict)
            else None
        )
        if cid is None:
            return
        key = str(int(cid))
        # update unread_by_chat (append under lock)
        try:
            with lock:
                unread = state.setdefault("unread_by_chat", {}).setdefault(key, [])
                unread.append(msg_shape["message"])
        except Exception:
            logger.exception("error updating unread_by_chat")

        # push to thread-safe queue for step() to consume
        try:
            pending_q.put_nowait(
                {
                    "type": "update",
                    "update": {"chat_id": cid, "message": msg_shape["message"]},
                }
            )
        except Exception:
            logger.exception("failed to enqueue pending unit update")

    try:
        # Build app if missing
        if app is None:
            app = _build_ptb_app_from_params(params)
            state["ptb_app"] = app
            # Register message handler once
            app.add_handler(MessageHandler(filters.ALL, _ptb_message_handler))

        async def _do_start_if_needed():
            with lock:
                if state.get("ptb_app_task"):
                    state["_start_refcount"] = state.get("_start_refcount", 0) + 1
                    return {"type": "status", "status": "already_started"}
                state["_start_refcount"] = state.get("_start_refcount", 0) + 1

            try:
                # Prefer running run_polling in a dedicated thread via run_in_executor.
                polling_future = background_loop.run_in_executor(
                    None, lambda: app.run_polling(stop_signals=())
                )
                state["ptb_app_task"] = polling_future
                return {"type": "status", "status": "started"}
            except Exception:
                with lock:
                    state["_start_refcount"] = max(
                        0, state.get("_start_refcount", 1) - 1
                    )
                logger.exception("failed to start ptb app")
                raise

        async def _stop():
            # Decrement refcount and stop only when reaches zero
            with lock:
                task = state.get("ptb_app_task")
                refcount = max(0, state.get("_start_refcount", 0) - 1)
                state["_start_refcount"] = refcount

            if refcount > 0:
                return {
                    "type": "status",
                    "status": "stop_deferred",
                    "refcount": refcount,
                }

            try:
                await app.stop()
                await app.shutdown()
            except Exception:
                logger.exception("error stopping/shutting down app")

            task_obj = task
            try:
                if task_obj is not None:
                    # attempt to wait up to timeout_seconds for executor to finish
                    timeout_seconds = _int_param(
                        params.get("delivery_timeout_s"),
                        default=5,
                        minimum=1,
                        maximum=300,
                    )
                    if isinstance(task_obj, concurrent.futures.Future):
                        try:
                            task_obj.result(timeout=timeout_seconds)
                        except Exception:
                            pass
                    elif asyncio.isfuture(task_obj) or isinstance(
                        task_obj, asyncio.Future
                    ):
                        try:
                            await asyncio.wait_for(task_obj, timeout=timeout_seconds)
                        except Exception:
                            pass
            except Exception:
                logger.exception("error waiting for ptb_app_task to finish")

            with lock:
                state.pop("ptb_app", None)
                state.pop("ptb_app_task", None)
            return {"type": "status", "status": "stopped"}

        async def _get_unread_impl():
            # snapshot unread state under lock then process
            with lock:
                unread_snapshot = {
                    k: list(v) for k, v in (state.get("unread_by_chat") or {}).items()
                }
                last_read = {
                    str(k): v for k, v in (state.get("last_read_by_chat") or {}).items()
                }

            chats = []
            for chat_id_str, messages in unread_snapshot.items():
                try:
                    cid = int(chat_id_str)
                except (TypeError, ValueError):
                    continue
                normalized_msgs = [m for m in messages]
                chats.append(
                    {
                        "chat_id": cid,
                        "unread_count": len(normalized_msgs),
                        "chat": {"id": cid},
                        "messages": normalized_msgs,
                    }
                )

            payload = {"chats": chats, "last_read": last_read}
            mark_read = _param_bool(params.get("mark_read"), default=True)
            if mark_read:
                with lock:
                    unread = state.get("unread_by_chat", {}) or {}
                    for k, msgs in unread.items():
                        if msgs:
                            try:
                                cid = int(k)
                            except Exception:
                                continue
                            max_id = max(
                                int(m.get("id") or 0)
                                for m in msgs
                                if isinstance(m, dict)
                            )
                            state.setdefault("last_read_by_chat", {})[str(cid)] = max_id
                    state["unread_by_chat"] = {}
            return {"type": "update", "update": payload}

        async def _send_message_impl():
            if not isinstance(action_payload, dict):
                raise ValueError("send_message payload must be a dict")
            chat_id = action_payload.get("chat_id")
            message = action_payload.get("message")
            if chat_id is None or message is None:
                raise ValueError("send_message requires chat_id and message")

            bot = app.bot

            # Allow numeric chat ids, numeric strings, and username/channel strings (pass-through)
            if isinstance(chat_id, int):
                send_target = chat_id
            elif isinstance(chat_id, str):
                if chat_id.isdigit():
                    send_target = int(chat_id)
                else:
                    send_target = (
                        chat_id  # let PTB validate (e.g., '@channelname' or username)
                    )
            else:
                raise ValueError("send_message chat_id must be an integer or string")

            sent: Message = await bot.send_message(
                chat_id=send_target, text=str(message)
            )
            msg_shape = _normalize_message_to_tdlib_shape(sent)
            result_update = {"message": msg_shape.get("message")}
            wait_delivery = _param_bool(params.get("wait_for_delivery"), default=True)
            if wait_delivery:
                # Note: this waits for send completion not network-level delivery/read receipts.
                result_update["delivered"] = True
                result_update["new_message_id"] = msg_shape.get("message", {}).get("id")
            return {"type": "update", "update": result_update}

    except Exception as exc:
        logger.exception("unexpected error preparing PTB unit step")
        return (
            {
                "update": None,
                "status": None,
                "error": {"type": "error", "error": str(exc) or type(exc).__name__},
            },
            state,
        )

    # --- continuation of _ptb_unit_step: action dispatch and scheduling ---
    async def _raw_payload() -> dict[str, Any]:
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

            ptb_app = state.get("ptb_app")
            bot = getattr(ptb_app or app, "bot", None)
            if bot is None:
                return {
                    "type": "error",
                    "error": "bot not initialized; start the bot first",
                }

            # Disallow private/dunder attributes for safety
            if method.startswith("_") or method.startswith("__"):
                return {"type": "error", "error": "requested method not permitted"}

            def _maybe_await(result: Any) -> Awaitable[Any]:
                if inspect.isawaitable(result):
                    return result  # type: ignore[return-value]

                async def _wrap():
                    return result

                return _wrap()

            # Try a direct bot method first
            call_fn = getattr(bot, method, None)
            if callable(call_fn):
                try:
                    res_candidate = call_fn(**dict(method_params))
                    res = await _maybe_await(res_candidate)
                    return {"type": "update", "update": res}
                except Exception as exc:
                    return {"type": "error", "error": str(exc)}

            # Fallback: try bot.request if available but validate signature
            request_fn = getattr(bot, "request", None)
            if callable(request_fn):
                try:
                    # PTB internals vary; call as request(method, data=...) if supported
                    try:
                        res_candidate = request_fn(method, data=dict(method_params))
                    except TypeError:
                        # try signature request(Request) fallback - build a lightweight Request-like dict
                        res_candidate = request_fn(method, dict(method_params))
                    res = await _maybe_await(res_candidate)
                    return {"type": "update", "update": res}
                except Exception as exc:
                    return {"type": "error", "error": str(exc)}

            return {
                "type": "error",
                "error": "Requested method not available on bot",
            }

        return {"type": "update", "update": payload}

    # Determine action name (explicit in payload preferred)
    act = (
        action_payload.get("action")
        if isinstance(action_payload, dict) and "action" in action_payload
        else action_name
    )

    # For get_unread/send_message we will auto start -> perform -> stop if app not already running
    if act == "tg_start":
        coro = _do_start_if_needed()
    elif act == "tg_stop":
        with lock:
            # force stop by zeroing refcount and capturing task safely
            state["_start_refcount"] = 0
        coro = _stop()
    elif act == "get_unread":

        async def _get_unread_full():
            with lock:
                already_running = bool(state.get("ptb_app_task"))
                if not already_running:
                    # increment refcount now to reserve start
                    state["_start_refcount"] = state.get("_start_refcount", 0) + 1
            started_here = False
            if not already_running:
                try:
                    await _do_start_if_needed()
                    started_here = True
                except Exception:
                    # ensure we undo reservation
                    with lock:
                        state["_start_refcount"] = max(
                            0, state.get("_start_refcount", 1) - 1
                        )
                    raise
            try:
                res = await _get_unread_impl()
                return res
            finally:
                if started_here:
                    await _stop()

        coro = _get_unread_full()
    elif act == "send_message":

        async def _send_message_full():
            with lock:
                already_running = bool(state.get("ptb_app_task"))
                if not already_running:
                    state["_start_refcount"] = state.get("_start_refcount", 0) + 1
            started_here = False
            if not already_running:
                try:
                    await _do_start_if_needed()
                    started_here = True
                except Exception:
                    with lock:
                        state["_start_refcount"] = max(
                            0, state.get("_start_refcount", 1) - 1
                        )
                    raise
            try:
                res = await _send_message_impl()
                return res
            finally:
                if started_here:
                    await _stop()

        coro = _send_message_full()
    else:
        # raw requires explicit start/stop (do not auto-start)
        coro = _raw_payload()

    # Schedule coroutine on background loop with robust timeout and cancellation
    try:
        if not background_loop.is_running():
            raise RuntimeError("background loop not running")
        fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
        timeout = _int_param(
            params.get("delivery_timeout_s"), default=60, minimum=1, maximum=3600
        )
        try:
            result = fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            # Try to cancel the running coroutine to avoid orphaned tasks
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
            result = {"type": "error", "error": str(exc) or type(exc).__name__}
    except Exception as exc:
        return (
            {
                "update": None,
                "status": None,
                "error": {"type": "error", "error": str(exc) or type(exc).__name__},
            },
            state,
        )

    # Drain pending queue (thread-safe) into pending_unit_updates list (small batch)
    try:
        with lock:
            pending = state.setdefault("pending_unit_updates", [])
            pq = state.get("pending_unit_queue")
            if isinstance(pq, queue.Queue):
                drained = []
                try:
                    for _ in range(256):  # limit batch to avoid long lock hold
                        item = pq.get_nowait()
                        drained.append(item)
                except queue.Empty:
                    pass
                pending.extend(drained)
    except Exception:
        logger.exception("error draining pending queue")
        with lock:
            pending = state.setdefault("pending_unit_updates", [])

    # Prefer direct result for request/response actions; fallback to pending updates
    out_update = None
    out_status = None
    out_error = None

    # Normalize result to expected shape (ensure dict with 'type')
    if result is None:
        result = {"type": "status", "status": "no_result"}

    rtype = result.get("type")
    if rtype in ("update", "status", "error") and act in (
        "send_message",
        "get_unread",
        "tg_start",
        "tg_stop",
        "raw",
    ):
        # for request-response actions prefer returning the action result
        if rtype == "update":
            out_update = result
        elif rtype == "status":
            out_status = result
        else:
            out_error = result
    else:
        # otherwise, emit pending update if available, else the result
        if pending:
            out_update = pending.pop(0)
        else:
            if rtype == "update":
                out_update = result
            elif rtype == "status":
                out_status = result
            elif rtype == "error":
                out_error = result
            else:
                out_status = {"type": "status", "status": "unknown_result"}

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
                "Bot-mode Telegram client using python-telegram-bot (long-polling). Input ports: tg_start, tg_stop, get_unread, send_message, raw. "
                "Tracks incoming updates via handlers and exposes get_unread similar to TDLib unit."
            ),
        )
    )
