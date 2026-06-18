"""TelegramBot unit: interact with an external telegram server via python-telegram-bot client.
   Requires: https://github.com/python-telegram-bot/python-telegram-bot
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
import logging
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
    bg = params.get("_background_loop") or params.get("_executor_loop")
    if isinstance(bg, asyncio.AbstractEventLoop):
        return bg
    exec_obj = params.get("_executor")
    if exec_obj is not None:
        bg = (
            getattr(exec_obj, "background_loop", None)
            or getattr(exec_obj, "loop", None)
            or getattr(exec_obj, "_loop", None)
        )
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
    """
    Produce a minimal TDLib-like message dict:
    {
      "id": <int>,
      "chat": {"id": <int>},
      "content": {"@type": "messageText", "text": {"text": "<text>"}},
      "date": <unix_ts>,
      "from": { ... }
    }
    """
    chat_id = msg.chat.id if msg.chat else None
    text = msg.text or msg.caption or ""
    content = {"@type": "messageText", "text": {"text": text}}
    return {
        "id": int(msg.message_id) if msg.message_id is not None else None,
        "chat_id": int(chat_id) if chat_id is not None else None,
        "message": {
            "id": int(msg.message_id) if msg.message_id is not None else None,
            "chat_id": int(chat_id) if chat_id is not None else None,
            "content": content,
            "date": int(msg.date.timestamp()) if msg.date is not None else None,
            "from": {"id": msg.from_user.id} if msg.from_user else None,
        },
    }


def _build_ptb_app_from_params(params: Dict[str, Any]) -> Application:
    bot_token = params.get("bot_token") or params.get(
        "account"
    )  # accept account as alias
    if not bot_token:
        raise ValueError("bot_token param required for Bot API unit")
    # PTB ApplicationBuilder expects "token" or use ApplicationBuilder().token(token)
    app = ApplicationBuilder().token(str(bot_token)).build()
    return app


def _collect_chats_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    chats_out: List[Dict[str, Any]] = []
    unread_by_chat = state.setdefault("unread_by_chat", {})
    # last_read = state.get("last_read_by_chat", {})
    for chat_id_str, messages in unread_by_chat.items():
        try:
            cid = int(chat_id_str)
        except (TypeError, ValueError):
            continue
        normalized_msgs = []
        for m in messages:
            # messages already stored in TDLib-like shape via handler
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


def _ptb_unit_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> tuple[Dict[str, Any], Dict[str, Any]]:

    # Determine action (same priority order)
    action_payload = None
    action_name = None
    for port_name in ("tg_start", "tg_stop", "get_unread", "send_message", "raw"):
        if port_name in inputs and inputs[port_name] is not None:
            raw_in = inputs[port_name]
            if isinstance(raw_in, dict):
                action_payload = raw_in
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
                    "error": "Background event loop not provided in params('_executor') or params('_executor_loop').",
                },
            },
            state,
        )

    # Ensure state keys
    state.setdefault("unread_by_chat", {})  # dict[str(chat_id)] -> list[message dict]
    state.setdefault("last_read_by_chat", {})

    app: Application | None = state.get("ptb_app")
    # app_task: asyncio.Task | None = state.get("ptb_app_task")

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
        unread = state.setdefault("unread_by_chat", {}).setdefault(key, [])
        unread.append(msg_shape["message"])
        # update last_read_by_chat if not present (we don't mark as read automatically)
        # Emit immediate unit update: store into a queue in state for retrieval by step()
        pending = state.setdefault("pending_unit_updates", [])
        pending.append(
            {
                "type": "update",
                "update": {"chat_id": cid, "message": msg_shape["message"]},
            }
        )

    try:
        # Build app if missing
        if app is None:
            app = _build_ptb_app_from_params(params)
            state["ptb_app"] = app
            # Register message handler
            app.add_handler(MessageHandler(filters.ALL, _ptb_message_handler))

        async def _start():
            # PTB Application.run_polling is a blocking convenience wrapper; instead start it manually
            # Start the application (initializes bot, dispatcher). Then create a task to run polling loop.
            await app.initialize()
            await app.start()
            # Run the blocking run_polling() in a separate thread via the background loop's executor.
            # store the returned Future-like task in state for later cancellation if needed
            polling_future = background_loop.run_in_executor(
                None, lambda: app.run_polling()
            )
            state["ptb_polling_future"] = polling_future

            # No async polling runner needed; provide an async placeholder to await the future if required
            async def _polling_runner_placeholder():
                try:
                    await polling_future
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Polling runner exited with exception")
                finally:
                    # attempt graceful shutdown of the app
                    try:
                        await app.stop()
                        await app.shutdown()
                    except Exception:
                        pass

            # schedule blocking run_polling() in a thread via the background loop's executor
            polling_future = background_loop.run_in_executor(
                None, lambda: app.run_polling()
            )
            state["ptb_app_task"] = polling_future
            return {"type": "status", "status": "started"}

        async def _stop():
            # stop polling task if present
            task = state.get("ptb_app_task")
            if isinstance(task, concurrent.futures.Future):
                try:
                    task.cancel()
                except Exception:
                    pass
            # Stop and shutdown app gracefully
            try:
                await app.stop()
                await app.shutdown()
            except Exception:
                pass
            # clear state
            state.pop("ptb_app", None)
            state.pop("ptb_app_task", None)
            state.pop("unread_by_chat", None)
            state.pop("last_read_by_chat", None)
            state.pop("pending_unit_updates", None)
            return {"type": "status", "status": "stopped"}

        async def _get_unread():
            # Ensure we are running (app exists)
            chats = _collect_chats_from_state(state)
            last_read = {
                str(k): v for k, v in (state.get("last_read_by_chat") or {}).items()
            }
            payload = {"chats": chats, "last_read": last_read}
            # If mark_read true, clear unread_by_chat and update last_read_by_chat
            mark_read = _param_bool(params.get("mark_read"), default=True)
            if mark_read:
                unread = state.get("unread_by_chat", {}) or {}
                for k, msgs in unread.items():
                    if msgs:
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

        async def _send_message():
            if not isinstance(action_payload, dict):
                raise ValueError("send_message payload must be a dict")
            chat_id = action_payload.get("chat_id")
            message = action_payload.get("message")
            if chat_id is None or message is None:
                raise ValueError("send_message requires chat_id and message")
            # Strict numeric chat id
            if isinstance(chat_id, int):
                send_target = chat_id
            elif isinstance(chat_id, str) and chat_id.isdigit():
                send_target = int(chat_id)
            else:
                raise ValueError(
                    "send_message chat_id must be an integer or numeric string"
                )

            bot = app.bot
            # PTB send_message returns telegram.Message
            sent: Message = await bot.send_message(
                chat_id=send_target, text=str(message)
            )
            # Map to TDLib-like shape
            msg_shape = _normalize_message_to_tdlib_shape(sent)
            result_update = {"message": msg_shape.get("message")}
            # delivered semantics: Bot API returns the sent message synchronously -> treat as delivered
            wait_delivery = _param_bool(params.get("wait_for_delivery"), default=True)
            if wait_delivery:
                result_update["delivered"] = True
                result_update["new_message_id"] = msg_shape.get("message", {}).get("id")
            return {"type": "update", "update": result_update}

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

                bot = app.bot

                def _maybe_await(result: Any) -> Awaitable[Any]:
                    if hasattr(result, "__await__"):
                        return result  # type: ignore[return-value]

                    async def _wrap():
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
                        res_candidate = request_fn(method, data=dict(method_params))
                        res = await _maybe_await(res_candidate)
                        return {"type": "update", "update": res}
                    except Exception as exc:
                        return {"type": "error", "error": str(exc)}

                return {
                    "type": "error",
                    "error": "Requested method not available on bot",
                }

            return {"type": "update", "update": payload}

        act = (
            action_payload.get("action")
            if isinstance(action_payload, dict) and "action" in action_payload
            else action_name
        )
        if act == "tg_start":
            coro = _start()
        elif act == "tg_stop":
            coro = _stop()
        elif act in ("get_unread", "get_chats"):
            coro = _get_unread()
        elif act == "send_message":
            coro = _send_message()
        else:
            coro = _raw_payload()

        # Schedule coroutine on background loop
        try:
            if not background_loop.is_running():
                raise RuntimeError("background loop not running")
            fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
            result = fut.result()
        except (RuntimeError, concurrent.futures.CancelledError):
            # fallback to synchronous run here (rare)
            try:
                result = asyncio.run(coro)
            except RuntimeError:
                raise

    except Exception as exc:
        return (
            {
                "update": None,
                "status": None,
                "error": {"type": "error", "error": str(exc) or type(exc).__name__},
            },
            state,
        )

    # If there are pending immediate unit updates from handlers, surface the first one
    pending = state.setdefault("pending_unit_updates", [])
    out_update = None
    out_status = None
    out_error = None
    if pending:
        out_update = pending.pop(0)
    else:
        if result is None:
            out_status = {"type": "status", "status": "no_result"}
        else:
            t = result.get("type")
            if t == "update":
                out_update = result
            elif t == "status":
                out_status = result
            elif t == "error":
                out_error = result

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
