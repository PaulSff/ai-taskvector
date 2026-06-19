"""
TelegramBotPoller: interact with an external telegram server via python-telegram-bot client.
   Requires: https://github.com/python-telegram-bot/python-telegram-bot >= v20+
   Installation: pip install python-telegram-bot --upgrade
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import logging
import os
import threading
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from telegram import Message, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from gui.components.settings import get_mydata_dir

from .helpers import (
    _load_json,
    _normalize_message_to_tdlib_shape,
    _param_bool,
    _save_json_atomic,
    _ts_suffix_yy_dd_mm_ss,
)

logger = logging.getLogger(__name__)

# Get mydata directory from settings
MESSAGES_DIR = get_mydata_dir() / "tg_messages"
os.makedirs(MESSAGES_DIR, exist_ok=True)


class TelegramBotPoller:
    """
    Polls Telegram via python-telegram-bot (PTB) and emits events to an async subscriber.

    Public lifecycle:
      await start()
      await stop(force=False)

    Subscription:
      async for ev in poller.subscribe():
          ev is {"type":"update_batch","update":..., "status":..., "error":...}

    Public operations (also emitted into the same stream as update_batch):
      await get_unread(...)
      await send_message(...)
      await raw(method=..., params=...)
    """

    def __init__(self, params: Dict[str, Any]):
        self.params = dict(params or {})
        self._lock = threading.RLock()

        self._ptb_app: Optional[Application] = None
        self._ptb_started = False
        self._handlers_registered = False
        self._start_refcount = 0

        # File (one file per run/timestamp)
        self._messages_file = os.path.join(
            MESSAGES_DIR, f"tg_messages{_ts_suffix_yy_dd_mm_ss()}.json"
        )

        self._state: Dict[str, Any] = {}
        self._init_state_from_disk()

        # Event system: raw events -> batcher -> public subscriber queue
        self._raw_q: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
        self._event_q: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
        self._closed = False
        self._subscriber_taken = False
        self._batch_task: Optional[asyncio.Task] = None

    # ---------------- Persistence ----------------

    def _init_state_from_disk(self) -> None:
        with self._lock:
            if os.path.exists(self._messages_file):
                try:
                    loaded = _load_json(self._messages_file)
                    self._state = {
                        "version": loaded.get("version", 1),
                        "created_utc": loaded.get("created_utc", None),
                        "updated_utc": loaded.get("updated_utc", None),
                        "messages_by_chat_id": loaded.get("messages_by_chat_id", {})
                        or {},
                        "last_read_by_chat_id": loaded.get("last_read_by_chat_id", {})
                        or {},
                    }
                    return
                except Exception:
                    logger.exception("Failed to load tg_messages file; starting fresh.")

            self._state = {
                "version": 1,
                "created_utc": None,
                "updated_utc": None,
                "messages_by_chat_id": {},
                "last_read_by_chat_id": {},
            }

    def _persist_state_locked(self) -> None:
        now_utc = dt.datetime.now(dt.timezone.utc)
        self._state["updated_utc"] = now_utc.isoformat().replace("+00:00", "Z")

        if self._state.get("created_utc") is None:
            self._state["created_utc"] = self._state["updated_utc"]

        _save_json_atomic(self._messages_file, self._state)

    # ---------------- PTB construction ----------------

    def _build_ptb_app_from_params(self) -> Application:
        bot_token = self.params.get("bot_token") or self.params.get("account")
        if not bot_token:
            raise ValueError("bot_token param required for TelegramBotPoller")

        async def _log_req(request: httpx.Request) -> None:
            logger.info(
                "tg http request method=%s url=%s", request.method, str(request.url)
            )

        async def _log_resp(response: httpx.Response) -> None:
            req = response.request
            logger.info(
                "tg http response method=%s url=%s status=%s",
                req.method if req else None,
                str(req.url) if req else None,
                response.status_code,
            )

        req = HTTPXRequest(
            connect_timeout=float(self.params.get("connect_timeout", 10)),
            read_timeout=float(self.params.get("read_timeout", 20)),
            pool_timeout=float(self.params.get("pool_timeout", 5)),
            httpx_kwargs={
                "event_hooks": {
                    "request": [_log_req],
                    "response": [_log_resp],
                }
            },
        )
        return ApplicationBuilder().token(str(bot_token)).request(req).build()

    async def _ensure_app_and_handlers(self) -> Application:
        with self._lock:
            if self._ptb_app is None:
                self._ptb_app = self._build_ptb_app_from_params()

            app = self._ptb_app
            if not self._handlers_registered:
                try:
                    app.add_error_handler(self._ptb_error_handler)
                except Exception:
                    pass
                app.add_handler(MessageHandler(filters.ALL, self._ptb_message_handler))
                self._handlers_registered = True
            return app

    # ---------------- PTB handlers -> raw events ----------------

    async def _ptb_message_handler(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return

        msg_shape = _normalize_message_to_tdlib_shape(update.message)
        cid = msg_shape.get("chat_id")
        msg_id = msg_shape.get("id")
        if cid is None or msg_id is None:
            return

        chat_key = str(int(cid))
        msg_obj = msg_shape["message"]

        with self._lock:
            per_chat = self._state["messages_by_chat_id"].setdefault(chat_key, [])

            existing_ids = {m.get("id") for m in per_chat if isinstance(m, dict)}
            if int(msg_obj.get("id")) not in existing_ids:
                per_chat.append(msg_obj)
                self._persist_state_locked()

        await self._emit_raw(
            {"type": "update", "update": {"chat_id": cid, "message": msg_obj}}
        )

    async def _ptb_error_handler(
        self, update: object | None, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.exception("telegram handler error", exc_info=getattr(ctx, "error", None))
        # Optional: you can stream errors if you want; kept as log-only by default.
        # await self._emit_raw({"type":"error","error": str(getattr(ctx,"error",""))})

    # ---------------- Event publishing / batching ----------------

    async def _emit_raw(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        await self._raw_q.put(event)

    async def _batcher(self) -> None:
        try:
            while True:
                raw = await self._raw_q.get()
                if raw is None:
                    return

                out_update = None
                out_status = None
                out_error = None

                rtype = raw.get("type")
                if rtype == "update":
                    out_update = raw.get("update")
                elif rtype == "status":
                    out_status = raw.get("status", raw)
                elif rtype == "error":
                    out_error = raw.get("error", raw)
                else:
                    out_update = raw

                await self._event_q.put(
                    {
                        "type": "update_batch",
                        "update": out_update,
                        "status": out_status,
                        "error": out_error,
                    }
                )
        except asyncio.CancelledError:
            return

    def subscribe(self) -> AsyncIterator[Dict[str, Any]]:
        async def gen():
            if self._subscriber_taken:
                raise RuntimeError("Only one subscriber is supported.")
            self._subscriber_taken = True

            while True:
                ev = await self._event_q.get()
                if ev is None:
                    return
                yield ev

        return gen()

    # ---------------- Lifecycle ----------------

    async def _start_if_needed(self) -> Dict[str, Any]:
        with self._lock:
            if self._ptb_started:
                self._start_refcount += 1
                return {"type": "status", "status": "already_started"}
            self._start_refcount += 1

        app = await self._ensure_app_and_handlers()

        try:
            await app.initialize()
            await app.start()

            updater = getattr(app, "updater", None)
            if updater is None:
                raise RuntimeError("Application has no updater; cannot start polling")

            await updater.start_polling(allowed_updates=None)

            with self._lock:
                self._ptb_started = True

            with self._lock:
                if self._batch_task is None or self._batch_task.done():
                    self._batch_task = asyncio.create_task(self._batcher())

            return {"type": "status", "status": "started"}
        except Exception:
            try:
                await app.shutdown()
            except Exception:
                pass
            with self._lock:
                self._ptb_started = False
                self._start_refcount = max(0, self._start_refcount - 1)
            logger.exception("failed to start ptb app")
            raise

    async def _stop_if_possible(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            if not self._ptb_started:
                return {"type": "status", "status": "not_started"}

            self._start_refcount = 0 if force else max(0, self._start_refcount - 1)
            refcount = self._start_refcount
            if refcount > 0 and not force:
                return {
                    "type": "status",
                    "status": "stop_deferred",
                    "refcount": refcount,
                }

        app = self._ptb_app
        if app is None:
            with self._lock:
                self._ptb_started = False
            return {"type": "status", "status": "stopped"}

        try:
            updater = getattr(app, "updater", None)
            if updater is not None:
                res = updater.stop()
                if inspect.isawaitable(res):
                    await res

            res = app.stop()
            if inspect.isawaitable(res):
                await res

            await app.shutdown()
        finally:
            with self._lock:
                self._ptb_started = False

        return {"type": "status", "status": "stopped"}

    async def start(self) -> Dict[str, Any]:
        return await self._start_if_needed()

    async def stop(self, force: bool = False) -> Dict[str, Any]:
        res = await self._stop_if_possible(force=force)

        with self._lock:
            if not self._ptb_started:
                self._closed = True

        if self._closed:
            # Stop batcher + end subscriber iterator
            try:
                await self._raw_q.put(None)
            except Exception:
                pass
            try:
                await self._event_q.put(None)
            except Exception:
                pass

        return res

    # ---------------- Operations  ----------------

    async def get_unread(self) -> Dict[str, Any]:
        mark_read = _param_bool(self.params.get("mark_read"), default=True)

        with self._lock:
            messages_by_chat = {
                k: list(v)
                for k, v in self._state.get("messages_by_chat_id", {}).items()
            }
            last_read_by_chat = dict(self._state.get("last_read_by_chat_id", {}))

        chats: List[Dict[str, Any]] = []
        updates_to_apply: List[Tuple[str, int]] = []

        for chat_key, messages in messages_by_chat.items():
            try:
                cid = int(chat_key)
            except Exception:
                continue

            try:
                lr = int(last_read_by_chat.get(chat_key, 0) or 0)
            except Exception:
                lr = 0

            unread_msgs: List[Dict[str, Any]] = []
            max_id = lr
            for m in messages:
                if not isinstance(m, dict):
                    continue
                mid = m.get("id")
                try:
                    mid_i = int(mid) if mid is not None else None
                except Exception:
                    mid_i = None
                if mid_i is None:
                    continue
                if mid_i > lr:
                    unread_msgs.append(m)
                if mid_i > max_id:
                    max_id = mid_i

            chats.append(
                {
                    "chat_id": cid,
                    "unread_count": len(unread_msgs),
                    "chat": {"id": cid},
                    "messages": unread_msgs,
                }
            )
            if mark_read and unread_msgs:
                updates_to_apply.append((chat_key, max_id))

        payload = {"chats": chats, "last_read": last_read_by_chat}

        if mark_read and updates_to_apply:
            with self._lock:
                for chat_key, new_lr in updates_to_apply:
                    self._state["last_read_by_chat_id"][chat_key] = new_lr
                self._persist_state_locked()

        # stream update_batch
        await self._emit_raw({"type": "update", "update": payload})
        return {"type": "update", "update": payload}

    async def send_message(
        self,
        chat_id: int | str,
        message: Any,
        *,
        wait_for_delivery: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if wait_for_delivery is None:
            wait_for_delivery = _param_bool(
                self.params.get("wait_for_delivery"), default=True
            )

        app = self._ptb_app
        if app is None:
            raise RuntimeError("bot not initialized; start the bot first")

        bot = getattr(app, "bot", None)
        if bot is None:
            raise RuntimeError("bot not initialized; start the bot first")

        if isinstance(chat_id, int):
            send_target: int | str = chat_id
        elif isinstance(chat_id, str):
            send_target = int(chat_id) if chat_id.isdigit() else chat_id
        else:
            raise ValueError("chat_id must be an integer or string")

        sent: Message = await bot.send_message(chat_id=send_target, text=str(message))
        msg_shape = _normalize_message_to_tdlib_shape(sent)

        result_update: Dict[str, Any] = {"message": msg_shape.get("message")}
        if wait_for_delivery:
            result_update["delivered"] = True
            result_update["new_message_id"] = msg_shape.get("message", {}).get("id")

        await self._emit_raw({"type": "update", "update": result_update})
        return {"type": "update", "update": result_update}

    async def raw(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        payload_params: Any = params or {}
        if not isinstance(method, str):
            return {"type": "error", "error": "invalid method"}

        if not isinstance(payload_params, dict):
            return {"type": "error", "error": "invalid params"}

        app = self._ptb_app
        if app is None:
            return {
                "type": "error",
                "error": "bot not initialized; start the bot first",
            }

        bot = getattr(app, "bot", None)
        if bot is None:
            return {
                "type": "error",
                "error": "bot not initialized; start the bot first",
            }

        if method.startswith("_") or method.startswith("__"):
            return {"type": "error", "error": "requested method not permitted"}

        async def _maybe_await(result: Any) -> Any:
            if inspect.isawaitable(result):
                return await result
            return result

        call_fn = getattr(bot, method, None)
        if callable(call_fn):
            try:
                res_candidate = call_fn(**dict(payload_params))
                res = await _maybe_await(res_candidate)
                await self._emit_raw({"type": "update", "update": res})
                return {"type": "update", "update": res}
            except Exception as exc:
                return {"type": "error", "error": str(exc)}

        request_fn = getattr(bot, "request", None)
        if callable(request_fn):
            try:
                try:
                    res_candidate = request_fn(method, data=dict(payload_params))
                except TypeError:
                    res_candidate = request_fn(method, dict(payload_params))
                res = await _maybe_await(res_candidate)
                await self._emit_raw({"type": "update", "update": res})
                return {"type": "update", "update": res}
            except Exception as exc:
                return {"type": "error", "error": str(exc)}

        return {"type": "error", "error": "Requested method not available on bot"}
