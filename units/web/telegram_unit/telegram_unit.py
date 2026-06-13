"""TelegramClient unit: interact with local python-telegram client:
    Requires:
        1. python-telegram: https://github.com/alexander-akhmetov/python-telegram
        2. TDLIb: https://github.com/tdlib/td

Receives commands on the "data" input port.

Inputs (dict):
tg_start: {"action": "tg_start"}
tg_stop: {"action": "tg_stop"}
get_chats: {"action": "get_chats", "messenger": "telegram", "account": "<phone_or_bot>"}
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
"_needs_executor": bool (set true for async loop injection)

Streaming / async: This unit schedules async operations on executor background loop (params["_executor"] or params["_executor_loop"] / params["_background_loop"]). It requires "_needs_executor": True."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from units.registry import UnitSpec, register_unit

# Local python-telegram imports
from .telegram.client import Telegram
from .telegram.text import PlainText

# Input ports: one port per requested command
TELEGRAM_CLIENT_INPUT_PORTS = [
    ("tg_start", "Any"),
    ("tg_stop", "Any"),
    ("get_chats", "Any"),
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
    background_loop = None
    exec_obj = params.get("_executor")
    if exec_obj is not None:
        background_loop = getattr(exec_obj, "_loop", None)
    if background_loop is None:
        background_loop = params.get("_executor_loop") or params.get("_background_loop")
    return background_loop


def _telegram_client_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    TelegramClient unit step. Dedicated input ports:
      - tg_start, tg_stop, get_chats, send_message, raw
    Raw payloads are forwarded to tg_client.call_method when payload is a dict
    with keys: {"method": "<TDLibMethodName>", "params": {...}}; otherwise they are
    forwarded to tg_client.handle_update if available.
    Async ops scheduled on executor background loop (params["_executor"] or params["_executor_loop"]).
    """

    # Determine which action port was used (priority order)
    action_payload = None
    action_name = None
    for port_name in ("tg_start", "tg_stop", "get_chats", "send_message", "raw"):
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
            res = tg_client.login()
            wait_fn = getattr(res, "wait", None)
            if callable(wait_fn):
                try:
                    wait_fn()
                except Exception:
                    pass
            return {"type": "status", "status": "started"}

        async def _stop_client():
            try:
                tg_client.stop()
            except Exception:
                pass
            return {"type": "status", "status": "stopped"}

        async def _get_chats():
            res = tg_client.get_chats()
            res.wait()
            return {"type": "update", "update": res.update}

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

            res = tg_client.send_message(send_target, PlainText(str(message)))
            # Call wait() only if present (safe for both sync/future-like results)
            wait_fn = getattr(res, "wait", None)
            if callable(wait_fn):
                try:
                    wait_fn()
                except Exception:
                    pass

            update_val = getattr(res, "update", None)
            return {"type": "update", "update": update_val}

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
        elif act == "get_chats":
            coro = _get_chats()
        elif act == "send_message":
            coro = _send_message()
        else:
            coro = _raw_payload()

        fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
        result = fut.result()

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
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Interact with local python-telegram (tdlib) client. Input ports: tg_start, tg_stop, get_chats, send_message, raw. "
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
