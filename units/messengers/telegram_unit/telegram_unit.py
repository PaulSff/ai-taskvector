"""TelegramClient unit: interact with local python-telegram client:
    Requires:
        1. python-telegram: https://github.com/alexander-akhmetov/python-telegram
        2. TDLIb: https://github.com/tdlib/td

Receives commands on the "data" input port.

Inputs (dict):
tg_start: {"action": "tg_start"}
tg_stop: {"action": "tg_stop"}
get_unread: {"action": "get_unread", "messenger": "telegram", "account": "<phone_or_bot>"}
send_message: {"action": "send_message", "messenger": "telegram", "chat_id": <int_or_str>, "message": ""}
raw: any payload dict from supported tg API methods (forwarded to client.handle_update)

Outputs:

update: {"type":"update","update": } on success
status: {"type":"status","status":"..."} for start/stop/other statuses
error: {"type":"error","error":"..."} on failure

Params (must be provided in params dict):

api_id (str)
api_hash (str)
account (str) OR bot_token (str)
database_encryption_key (str)
files_directory (str)
library_path (str)
wait_for_delivery (bool, default true) — wait for updateMessageSendSucceeded after send_message
delivery_timeout_s (int, default 60) — max seconds to wait when wait_for_delivery is true
mark_read (bool, default true) — mark inbox read up to highest fetched message on get_unread
chat_list_limit (int, default 100) — page size when listing chats for get_unread
"_needs_executor": bool (set true for async loop injection)

Streaming / async: This unit schedules async operations on executor background loop (params["_executor"] or params["_executor_loop"] / params["_background_loop"]). It requires "_needs_executor": True."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from typing import Any, Dict

from units.registry import UnitSpec, register_unit

# Local python-telegram imports
from .telegram.client import AuthorizationState, Telegram
from .telegram.text import PlainText

logger = logging.getLogger(__name__)

# Input ports: one port per requested command
TELEGRAM_CLIENT_INPUT_PORTS = [
    ("tg_start", "Any"),
    ("tg_stop", "Any"),
    ("get_unread", "Any"),
    ("send_message", "Any"),
    (
        "raw",
        "Any",
    ),  # raw payload -> forwarded to tg_client.call_method when appropriate
]
TELEGRAM_CLIENT_OUTPUT_PORTS = [
    ("update", "Any"),
    ("status", "Any"),
    ("error", "Any"),
]


def _build_tg_client_from_params(params: Dict[str, Any]) -> Telegram:
    api_id = params.get("api_id")
    api_hash = params.get("api_hash")
    account = params.get("account")
    bot_token = params.get("bot_token")
    database_encryption_key = params.get("database_encryption_key")
    files_directory = params.get("files_directory")
    library_path = params.get("library_path")

    if api_id is None or api_hash is None or database_encryption_key is None:
        raise ValueError(
            "Missing required params: api_id, api_hash, database_encryption_key"
        )
    if not (account or bot_token):
        raise ValueError("Provide either account (phone) or bot_token")

    try:
        api_id_int = int(api_id)
    except (TypeError, ValueError):
        raise ValueError("api_id must be an integer or numeric string") from None

    client_kwargs = {
        "api_id": api_id_int,
        "api_hash": str(api_hash),
        "database_encryption_key": str(database_encryption_key),
    }
    if account:
        client_kwargs["phone"] = str(account)
    else:
        client_kwargs["bot_token"] = str(bot_token)
    if files_directory:
        client_kwargs["files_directory"] = str(files_directory)
    if library_path:
        client_kwargs["library_path"] = str(library_path)

    return Telegram(**client_kwargs)


def _resolve_background_loop(
    params: Dict[str, Any],
) -> asyncio.AbstractEventLoop | None:
    """Prefer explicit public loop params; fall back to executor public attributes."""
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


def _async_result_error_message(res: Any) -> str | None:
    if getattr(res, "error", False):
        info = getattr(res, "error_info", None)
        if isinstance(info, dict):
            return str(info.get("message") or info)
        if info is not None:
            return str(info)
        return "Telegram API error"
    return None


def _wait_async_result(
    res: Any,
    *,
    timeout: int | None = None,
    label: str = "",
) -> None:
    """Block on python-telegram AsyncResult; raise on timeout or TDLib error."""
    wait_fn = getattr(res, "wait", None)
    if not callable(wait_fn):
        return
    prefix = f"{label}: " if label else ""
    try:
        wait_fn(timeout=timeout, raise_exc=False)
    except TimeoutError as exc:
        raise TimeoutError(f"{prefix}timed out") from exc
    err = _async_result_error_message(res)
    if err:
        raise RuntimeError(f"{prefix}{err}")


def _ensure_telegram_session(tg_client: Telegram, state: Dict[str, Any]) -> None:
    """Login before API calls (required by python-telegram / TDLib)."""
    if tg_client.authorization_state == AuthorizationState.READY:
        state["telegram_logged_in"] = True
        return
    auth = tg_client.login(blocking=True)
    if auth != AuthorizationState.READY:
        raise RuntimeError(
            f"Telegram login not ready ({getattr(auth, 'name', auth)}); "
            "complete auth via tg_start or interactive login"
        )
    state["telegram_logged_in"] = True


def _preload_chats_if_needed(tg_client: Telegram, state: Dict[str, Any]) -> None:
    """
    Preload chat list into TDLib DB before send_message.

    Official python-telegram example: on first run the library must load chats or
    send_message fails because the chat is not in the local database yet.
    """
    if state.get("chats_preloaded"):
        return
    res = tg_client.get_chats()
    _wait_async_result(res, label="get_chats preload")
    state["chats_preloaded"] = True


def _wait_message_delivery(
    tg_client: Telegram,
    *,
    old_message_id: int,
    timeout_s: int,
) -> tuple[bool, int | None]:
    """Wait for updateMessageSendSucceeded (official send_message.py pattern)."""
    delivered_event = threading.Event()
    new_message_id: int | None = None

    def _on_send_succeeded(update: dict[str, Any]) -> None:
        nonlocal new_message_id
        if update.get("old_message_id") != old_message_id:
            return
        msg = update.get("message")
        if isinstance(msg, dict) and msg.get("id") is not None:
            new_message_id = int(msg["id"])
        delivered_event.set()

    tg_client.add_update_handler("updateMessageSendSucceeded", _on_send_succeeded)
    try:
        delivered = delivered_event.wait(timeout=max(1, timeout_s))
    finally:
        tg_client.remove_update_handler(
            "updateMessageSendSucceeded", _on_send_succeeded
        )
    return delivered, new_message_id


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


def _send_delivery_params(params: Dict[str, Any]) -> tuple[bool, int]:
    wait_delivery = _param_bool(params.get("wait_for_delivery"), default=True)
    raw_timeout = params.get("delivery_timeout_s", 60)
    try:
        timeout_s = int(raw_timeout if raw_timeout is not None else 60)
    except (TypeError, ValueError):
        timeout_s = 60
    return wait_delivery, max(1, timeout_s)


def _async_result_update(res: Any) -> Any:
    return getattr(res, "update", None)


def _extract_message_text(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if not isinstance(content, dict):
        return None
    if content.get("@type") != "messageText":
        return None
    text_obj = content.get("text")
    if isinstance(text_obj, dict):
        return str(text_obj.get("text") or "")
    if text_obj is not None:
        return str(text_obj)
    return None


def _int_param(
    value: Any, *, default: int, minimum: int = 1, maximum: int = 1000
) -> int:
    try:
        n = int(value if value is not None else default)
    except (TypeError, ValueError):
        n = default
    return max(minimum, min(n, maximum))


def _collect_chat_ids(tg_client: Telegram, *, page_limit: int) -> list[int]:
    """Page through TDLib chat list (getChats)."""
    chat_ids: list[int] = []
    offset_order = 2**63 - 1
    offset_chat_id = 0
    while True:
        res = tg_client.get_chats(
            offset_order=offset_order,
            offset_chat_id=offset_chat_id,
            limit=page_limit,
        )
        _wait_async_result(res, label="get_chats")
        update = _async_result_update(res)
        batch = update.get("chat_ids") if isinstance(update, dict) else None
        if not isinstance(batch, list) or not batch:
            break
        for cid in batch:
            try:
                chat_ids.append(int(cid))
            except (TypeError, ValueError):
                continue
        if len(batch) < page_limit:
            break
        offset_chat_id = int(batch[-1])
        chat_res = tg_client.get_chat(offset_chat_id)
        _wait_async_result(chat_res, label="get_chat")
        chat_update = _async_result_update(chat_res)
        if not isinstance(chat_update, dict) or chat_update.get("order") is None:
            break
        offset_order = int(chat_update["order"])
    return chat_ids


def _read_chat_inbox(
    tg_client: Telegram, *, chat_id: int, last_message_id: int
) -> None:
    read_res = tg_client.call_method(
        "readChatInbox",
        params={
            "chat_id": chat_id,
            "last_read_inbox_message_id": last_message_id,
        },
    )
    _wait_async_result(read_res, label="readChatInbox")


def _fetch_unread_messages(
    tg_client: Telegram,
    state: Dict[str, Any],
    params: Dict[str, Any],
) -> dict[str, Any]:
    """
    List chats with unread messages and return new messages since last_read (unit state).

    Mirrors the python-telegram unread-fetch pattern: get_chats → get_chat → get_chat_history
    → filter by last_read → optionally readChatInbox.
    """
    mark_read = _param_bool(params.get("mark_read"), default=True)
    page_limit = _int_param(params.get("chat_list_limit"), default=100)

    last_read_raw = state.get("last_read_by_chat") or {}
    last_read: dict[int, int] = {}
    if isinstance(last_read_raw, dict):
        for key, val in last_read_raw.items():
            try:
                last_read[int(key)] = int(val)
            except (TypeError, ValueError):
                continue

    chats_out: list[dict[str, Any]] = []
    for chat_id in _collect_chat_ids(tg_client, page_limit=page_limit):
        chat_res = tg_client.get_chat(chat_id)
        _wait_async_result(chat_res, label="get_chat")
        chat = _async_result_update(chat_res)
        if not isinstance(chat, dict):
            continue

        try:
            unread = int(chat.get("unread_count") or 0)
        except (TypeError, ValueError):
            unread = 0
        if unread <= 0:
            continue

        hist_res = tg_client.get_chat_history(
            chat_id=chat_id,
            from_message_id=0,
            offset=0,
            limit=unread,
            only_local=False,
        )
        _wait_async_result(hist_res, label="get_chat_history")
        hist = _async_result_update(hist_res)
        messages = hist.get("messages") if isinstance(hist, dict) else None
        if not isinstance(messages, list) or not messages:
            continue

        messages = list(reversed(messages))
        last_known = last_read.get(chat_id, 0)
        new_messages = [
            m
            for m in messages
            if isinstance(m, dict) and int(m.get("id") or 0) > last_known
        ]
        if not new_messages:
            continue

        normalized: list[dict[str, Any]] = []
        for m in new_messages:
            entry: dict[str, Any] = {
                "id": m.get("id"),
                "chat_id": chat_id,
                "message": m,
            }
            text = _extract_message_text(m)
            if text is not None:
                entry["text"] = text
            normalized.append(entry)

        max_id = max(int(m["id"]) for m in new_messages if m.get("id") is not None)
        last_read[chat_id] = max_id
        if mark_read:
            _read_chat_inbox(tg_client, chat_id=chat_id, last_message_id=max_id)

        chats_out.append(
            {
                "chat_id": chat_id,
                "unread_count": unread,
                "chat": chat,
                "messages": normalized,
            }
        )

    state["last_read_by_chat"] = last_read
    state["chats_preloaded"] = True
    return {
        "chats": chats_out,
        "last_read": {str(k): v for k, v in last_read.items()},
    }


def _telegram_client_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    TelegramClient unit step. Dedicated input ports:
      - tg_start, tg_stop, get_unread, send_message, raw
    Raw payloads are forwarded to tg_client.call_method when payload is a dict
    with keys: {"method": "<TDLibMethodName>", "params": {...}}; otherwise they are
    forwarded to tg_client.handle_update if available.
    Async ops scheduled on executor background loop (params["_executor"] or params["_executor_loop"]).
    """

    # Determine which action port was used (priority order)
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
    logger.debug(
        "Resolved background loop id=%s running=%s thread=%s",
        id(background_loop) if background_loop is not None else None,
        getattr(background_loop, "is_running", lambda: False)(),
        threading.get_ident(),
    )
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

    tg_client = state.get("tg_client")
    try:
        # If client missing, allow account override from payload then build client
        if tg_client is None:
            if (
                isinstance(action_payload, dict)
                and "account" in action_payload
                and "account" not in params
            ):
                params = {**params, "account": action_payload.get("account")}
            tg_client = _build_tg_client_from_params(params)
            state["tg_client"] = tg_client

        async def _start_client():
            auth = tg_client.login(blocking=True)
            state["telegram_logged_in"] = auth == AuthorizationState.READY
            if auth != AuthorizationState.READY:
                return {
                    "type": "status",
                    "status": getattr(auth, "name", str(auth)).lower(),
                }
            return {"type": "status", "status": "started"}

        async def _stop_client():
            try:
                tg_client.stop()
            except Exception:
                pass
            state.pop("chats_preloaded", None)
            state.pop("telegram_logged_in", None)
            state.pop("last_read_by_chat", None)
            return {"type": "status", "status": "stopped"}

        async def _get_unread():
            _ensure_telegram_session(tg_client, state)
            payload = _fetch_unread_messages(tg_client, state, params)
            return {"type": "update", "update": payload}

        async def _send_message():
            if not isinstance(action_payload, dict):
                raise ValueError("send_message payload must be a dict")
            chat_id = action_payload.get("chat_id")
            message = action_payload.get("message")
            if chat_id is None or message is None:
                raise ValueError("send_message requires chat_id and message")

            # Strictly require numeric chat_id (int or numeric string)
            if isinstance(chat_id, int):
                send_target = chat_id
            elif isinstance(chat_id, str) and chat_id.isdigit():
                send_target = int(chat_id)
            else:
                raise ValueError(
                    "send_message chat_id must be an integer or numeric string"
                )

            _ensure_telegram_session(tg_client, state)
            _preload_chats_if_needed(tg_client, state)

            send_res = tg_client.send_message(send_target, PlainText(str(message)))
            _wait_async_result(send_res, label="send_message")

            update_val = getattr(send_res, "update", None)
            wait_delivery, timeout_s = _send_delivery_params(params)

            delivered = False
            new_message_id: int | None = None
            old_message_id = (
                update_val.get("id")
                if isinstance(update_val, dict) and update_val.get("id") is not None
                else None
            )
            if wait_delivery and old_message_id is not None:
                delivered, new_message_id = _wait_message_delivery(
                    tg_client,
                    old_message_id=int(old_message_id),
                    timeout_s=timeout_s,
                )

            result_update: dict[str, Any] = {"message": update_val}
            if old_message_id is not None:
                result_update["old_message_id"] = old_message_id
            if wait_delivery:
                result_update["delivered"] = delivered
                if new_message_id is not None:
                    result_update["new_message_id"] = new_message_id
            return {"type": "update", "update": result_update}

        async def _raw_payload():
            """
            Raw handling policy:
            - If payload is a dict with keys {"method": "<name>", "params": {...}},
              call tg_client.call_method(method, params=...) and return its result.
            - Else if tg_client has handle_update(), call it with the payload.
            - Otherwise return the payload as-is.
            """
            payload = action_payload if action_payload is not None else {}
            # If payload explicitly requests a method call
            if isinstance(payload, dict) and "method" in payload:
                method_name = payload.get("method")
                method_params = payload.get("params", {}) or {}
                if not isinstance(method_name, str):
                    return {
                        "type": "error",
                        "error": "raw payload 'method' must be a string",
                    }
                call = getattr(tg_client, "call_method", None)
                if not callable(call):
                    return {
                        "type": "error",
                        "error": "tg_client.call_method not available on this client",
                    }
                try:
                    call_res = call(method_name, params=method_params)
                except Exception as exc:
                    return {"type": "error", "error": str(exc)}

                # If the result has a wait() method, call it; otherwise treat as immediate result.
                wait_fn = getattr(call_res, "wait", None)
                if callable(wait_fn):
                    try:
                        wait_fn()
                    except Exception:
                        # ignore wait errors; proceed to extract result if available
                        pass

                # Prefer .update attribute if present, else return the call_res itself
                update_val = getattr(call_res, "update", None)
                if update_val is not None:
                    return {"type": "update", "update": update_val}
                return {"type": "update", "update": call_res}

            # Fallback to handle_update if available
            handler = getattr(tg_client, "handle_update", None)
            if callable(handler):
                try:
                    handler(payload)
                    return {"type": "update", "update": payload}
                except Exception as exc:
                    return {"type": "error", "error": str(exc)}
            return {"type": "update", "update": payload}

        act = (
            action_payload.get("action")
            if isinstance(action_payload, dict) and "action" in action_payload
            else action_name
        )
        if act == "tg_start":
            coro = _start_client()
        elif act == "tg_stop":
            coro = _stop_client()
        elif act in ("get_unread", "get_chats"):
            coro = _get_unread()
        elif act == "send_message":
            coro = _send_message()
        else:
            coro = _raw_payload()

        # Defensive scheduling: ensure loop is running and handle shutdown races.
        try:
            if (
                not isinstance(background_loop, asyncio.AbstractEventLoop)
                or not background_loop.is_running()
            ):
                raise RuntimeError("background loop not running")
            fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
            result = fut.result()
        except (RuntimeError, concurrent.futures.CancelledError) as e:
            logger.warning(
                "Background loop unavailable or shutting down (id=%s); falling back to synchronous execution: %s",
                id(background_loop) if background_loop is not None else None,
                e,
            )
            # Fallback: run the coroutine synchronously in this thread.
            try:
                # If there's already a running loop in this thread, asyncio.run will fail.
                # In that case, surface error to outer handler so unit returns an error rather than scheduling on a closing loop.
                result = asyncio.run(coro)
            except RuntimeError as e2:
                logger.error(
                    "Synchronous fallback failed due to running event loop: %s", e2
                )
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

    out_update = None
    out_status = None
    out_error = None
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


def register_telegram_client() -> None:
    register_unit(
        UnitSpec(
            type_name="TelegramClient",
            input_ports=TELEGRAM_CLIENT_INPUT_PORTS,
            output_ports=TELEGRAM_CLIENT_OUTPUT_PORTS,
            step_fn=_telegram_client_step,
            environment_tags=["messengers"],
            environment_tags_are_agnostic=False,
            description=(
                "Interact with local python-telegram (tdlib) client. Input ports: tg_start, tg_stop, get_unread, send_message, raw. "
                "get_unread fetches chats with unread messages and their message bodies (tracks last_read in unit state). "
                "Raw dicts with {'method': '<name>', 'params': {...}} are executed with tg_client.call_method(...). "
                "Schedules async operations on executor background loop; requires params['_needs_executor']=True "
                "and either params['_executor'] (GraphExecutor) or params['_executor_loop'] / params['_background_loop']."
            ),
        )
    )


__all__ = [
    "register_telegram_client",
    "TELEGRAM_CLIENT_INPUT_PORTS",
    "TELEGRAM_CLIENT_OUTPUT_PORTS",
]
