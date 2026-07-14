# runtime/telegram_bot_poller.py
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import glob
import inspect
import logging
import os
import re
import signal
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
from telegram.error import Forbidden

from gui.components.settings import (
    get_telegram_bot_poller_lock_file_path,
    get_telegram_conversations_dir,
)
from runtime.zmq_messaging import ZmqPublisher, ZmqTopics

from .helpers import (
    _load_json,
    _normalize_message_to_tdlib_shape,
    _param_bool,
    _save_json_atomic,
    _ts_suffix_yy_dd_mm_ss,
    default_conf,
    get_zmq_update_endpoint,
    load_conf_yaml,
    get_blacklist_file,
)
from .single_instance_lock import SingleInstanceLock

logger = logging.getLogger(__name__)

MESSAGES_DIR = get_telegram_conversations_dir()
os.makedirs(MESSAGES_DIR, exist_ok=True)

MAX_MESSAGES_PER_CHAT = int(os.environ.get("TG_MAX_MESSAGES_PER_CHAT", "200"))

conf = load_conf_yaml(os.environ.get("CONF_YAML_PATH", default_conf))
DEFAULT_ZMQ_PUB_ENDPOINT = get_zmq_update_endpoint(conf)

BLACKLIST_FILE = os.path.join(MESSAGES_DIR, get_blacklist_file(conf))

os.makedirs(os.path.dirname(BLACKLIST_FILE), exist_ok=True)

needs_init = (not os.path.exists(BLACKLIST_FILE)) or (os.path.getsize(BLACKLIST_FILE) == 0)
if needs_init:
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        f.write("{}")


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

        self._instance_lock = SingleInstanceLock(
            get_telegram_bot_poller_lock_file_path()
        )
        self._instance_lock_acquired = False
        self._orig_sigint: Optional[Any] = None
        self._orig_sigterm: Optional[Any] = None
        self._shutdown_registered = False

        # ZMQ publisher (optional)
        self._zmq_pub_endpoint = (
            self.params.get("update_endpoint") or DEFAULT_ZMQ_PUB_ENDPOINT
        )
        # self._zmq_pub_endpoint: Optional[str] = "tcp://127.0.0.1:5556"
        # self._zmq_pub_endpoint: Optional[str] = self.params.get("update_endpoint")
        self._zmq_publisher: Optional[ZmqPublisher] = None
        # Re-connect
        self._reconnect_task: Optional[asyncio.Task] = None
        self._stop_requested = False

        self._cache_dirty = False
        self._cache_valid = False
        self._blacklist: Dict[str, Dict[str, int]] = {}  # {bot_account: {chat_id_str: blocked_epoch_s}}
        self._blacklist_loaded = False

    # ---------------- Handle network ----------------

    def _is_transient_network_exc(self, exc: BaseException) -> bool:
        s = str(exc).lower()
        transient_markers = (
            "timed out",
            "timeout",
            "temporary failure",
            "network is unreachable",
            "connection reset",
            "connection aborted",
            "connect",
            "ssl",
            "read_timeout",
            "pool timeout",
            "httpx",
            "proxy",
        )
        return isinstance(exc, (httpx.HTTPError, OSError)) or any(
            m in s for m in transient_markers
        )

    async def _reconnect_loop(self) -> None:
        delay = float(self.params.get("reconnect_initial_delay", 1.0))
        max_delay = float(self.params.get("reconnect_max_delay", 60.0))

        while not self._stop_requested:
            try:
                with self._lock:
                    if self._closed:
                        return

                    # If something else already restarted it, just wait for future failures
                    if self._ptb_started:
                        await asyncio.sleep(0.5)
                        continue

                with self._lock:
                    # Mark as not started so _start_if_needed will run again
                    self._ptb_started = False

                await self._start_if_needed()

                # Successful start: reset backoff
                delay = float(self.params.get("reconnect_initial_delay", 1.0))
                # Keep looping; you may still get later disconnects
                await asyncio.sleep(0.5)
            except Exception as exc:
                # Always continue reconnecting forever
                if self._is_transient_network_exc(exc):
                    with contextlib.suppress(Exception):
                        await self._emit_raw(
                            {
                                "type": "status",
                                "status": "reconnecting",
                                "error": str(exc),
                            }
                        )
                else:
                    with contextlib.suppress(Exception):
                        await self._emit_raw(
                            {
                                "type": "status",
                                "status": "reconnecting_after_error",
                                "error": str(exc),
                            }
                        )

                await asyncio.sleep(delay)
                delay = min(max_delay, delay * 2)

    # ---------------- Ensure one single instance running ----------------

    def _register_signal_handlers(self) -> None:
        if self._shutdown_registered:
            return
        self._shutdown_registered = True

        def _handle(sig, frame):
            # Fire-and-forget: we just trigger stop()
            try:
                asyncio.get_running_loop().create_task(self.stop(force=True))
            except RuntimeError:
                # No running loop: fall back to blocking stop
                try:
                    asyncio.run(self.stop(force=True))
                except Exception:
                    pass

            # Chain to the original handler if it was not SIG_IGN
            handler = self._orig_sigterm if sig == signal.SIGTERM else self._orig_sigint
            if handler not in (None, signal.SIG_IGN, signal.SIG_DFL):
                with contextlib.suppress(Exception):
                    handler(sig, frame)

        self._orig_sigint = signal.getsignal(signal.SIGINT)
        self._orig_sigterm = signal.getsignal(signal.SIGTERM)

        with contextlib.suppress(Exception):
            signal.signal(signal.SIGINT, _handle)
            signal.signal(signal.SIGTERM, _handle)

    def _maybe_release_lock(self) -> None:
        if self._instance_lock_acquired:
            self._instance_lock.release()
            self._instance_lock_acquired = False

    def _require_instance_owner(self) -> None:
        if not getattr(self, "_instance_lock_acquired", False):
            raise RuntimeError(
                "TelegramBotPoller instance lock not held (not the active instance)"
            )

    # ---------------- Persistence ----------------

    def _init_state_from_disk(self) -> None:
        with self._lock:
            pattern = os.path.join(MESSAGES_DIR, "tg_messages*.json")
            candidates = glob.glob(pattern)
            latest = max(candidates, key=os.path.getmtime) if candidates else None

            logger.info(
                "TelegramBotPoller: init_state_from_disk: pattern=%s latest=%s candidates=%d",
                pattern,
                latest,
                len(candidates),
            )

            # Base empty state
            self._messages_file = os.path.join(
                MESSAGES_DIR, f"tg_messages{_ts_suffix_yy_dd_mm_ss()}.json"
            )
            self._state = {
                "version": 1,
                "created_utc": None,
                "updated_utc": None,
                "messages_by_chat_id": {},
                "last_read_by_chat_id": {},
            }

            # If we have an existing file, load it and keep writing to it
            if latest:
                try:
                    loaded = _load_json(latest)
                    self._messages_file = latest
                    self._state = {
                        "version": loaded.get("version", 1),
                        "created_utc": loaded.get("created_utc", None),
                        "updated_utc": loaded.get("updated_utc", None),
                        "messages_by_chat_id": loaded.get("messages_by_chat_id", {})
                        or {},
                        "last_read_by_chat_id": loaded.get("last_read_by_chat_id", {})
                        or {},
                    }
                    logger.info(
                        "TelegramBotPoller: init_state_from_disk: loaded messages_by_chat_id_len=%d last_read_len=%d",
                        len(self._state.get("messages_by_chat_id", {}) or {}),
                        len(self._state.get("last_read_by_chat_id", {}) or {}),
                    )
                except Exception:
                    logger.exception(
                        "Failed to load latest tg_messages file; starting fresh."
                    )

    def _load_state_from_disk_locked(self) -> Dict[str, Any]:
        pattern = os.path.join(MESSAGES_DIR, "tg_messages*.json")
        candidates = glob.glob(pattern)
        state: Dict[str, Any] = {
            "version": 1,
            "created_utc": None,
            "updated_utc": None,
            "messages_by_chat_id": {},
            "last_read_by_chat_id": {},
        }

        if not candidates:
            return state

        latest = max(candidates, key=os.path.getmtime)
        self._messages_file = latest

        loaded = _load_json(latest)
        state = {
            "version": loaded.get("version", 1),
            "created_utc": loaded.get("created_utc", None),
            "updated_utc": loaded.get("updated_utc", None),
            "messages_by_chat_id": loaded.get("messages_by_chat_id", {}) or {},
            "last_read_by_chat_id": loaded.get("last_read_by_chat_id", {}) or {},
        }
        return state

    def _persist_state_locked(self) -> None:
        now_utc = dt.datetime.now(dt.timezone.utc)
        self._state["updated_utc"] = now_utc.isoformat().replace("+00:00", "Z")

        if self._state.get("created_utc") is None:
            self._state["created_utc"] = self._state["updated_utc"]

        _save_json_atomic(self._messages_file, self._state)

    def _bot_account_key(self) -> str:
        return str(self.params.get("bot_token") or self.params.get("account") or "")

    def _load_blacklist_locked(self) -> None:
        if self._blacklist_loaded:
            return
        self._blacklist_loaded = True
        self._blacklist = {}

        if not os.path.exists(BLACKLIST_FILE):
            return

        try:
            loaded = _load_json(BLACKLIST_FILE)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    account_key = str(k)
                    if isinstance(v, dict):
                        self._blacklist[account_key] = {
                            str(chat_id): int(ts)
                            for chat_id, ts in v.items()
                            if ts is not None
                        }
        except Exception:
            logger.exception("Failed to load tg_black_list.json; starting empty.")
            self._blacklist = {}


    def _persist_blacklist_locked(self) -> None:
        _save_json_atomic(BLACKLIST_FILE, self._blacklist)

    def _is_chat_blacklisted_locked(self, chat_id: int | str) -> bool:
        self._load_blacklist_locked()
        key = self._bot_account_key()
        return str(chat_id) in (self._blacklist.get(key, {}) or {})


    def _add_chat_to_blacklist_locked(self, chat_id: int | str) -> None:
        self._load_blacklist_locked()
        key = self._bot_account_key()
        chat_s = str(chat_id)

        now_utc = dt.datetime.now(dt.timezone.utc)
        blocked_epoch_s = int(now_utc.timestamp())

        self._blacklist.setdefault(key, {})
        self._blacklist[key][chat_s] = blocked_epoch_s
        self._persist_blacklist_locked()

    def _remove_chat_from_blacklist_locked(self, chat_id: int | str) -> None:
        self._load_blacklist_locked()
        key = self._bot_account_key()
        chat_s = str(chat_id)

        block_map = self._blacklist.get(key, {}) or {}
        if chat_s not in block_map:
            return

        block_map.pop(chat_s, None)
        if block_map:
            self._blacklist[key] = block_map
        else:
            self._blacklist.pop(key, None)

        self._persist_blacklist_locked()

    # ---------------- PTB construction ----------------

    def _build_ptb_app_from_params(self) -> Application:
        bot_token = self.params.get("bot_token") or self.params.get("account")
        if not bot_token:
            raise ValueError("bot_token param required for TelegramBotPoller")

        async def _log_req(request: httpx.Request) -> None:
            logger.info(
                "TelegramBotPoller: http request method=%s url=%s",
                request.method,
                str(request.url),
            )

        async def _log_resp(response: httpx.Response) -> None:
            req = response.request
            logger.info(
                "TelegramBotPoller: http response method=%s url=%s status=%s",
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
            self._state = self._load_state_from_disk_locked()

            per_chat = self._state["messages_by_chat_id"].setdefault(chat_key, [])
            existing_ids = {
                m.get("id")
                for m in per_chat
                if isinstance(m, dict) and m.get("id") is not None
            }

            new_id = msg_obj.get("id")
            if new_id is None:
                # can't dedupe or sort reliably; just append + truncate
                per_chat.append(msg_obj)
            else:
                if new_id not in existing_ids:
                    per_chat.append(msg_obj)
                else:
                    # duplicate message, nothing to do
                    new_id = None

            if new_id is not None or per_chat:

                def msg_sort_key(m: Any) -> int:
                    if not isinstance(m, dict):
                        return -1
                    v = m.get("id")
                    try:
                        return int(v) if v is not None else -1
                    except Exception:
                        return -1

                # Keep only last N messages (by id if possible)
                try:
                    per_chat.sort(key=msg_sort_key)
                except Exception:
                    pass

                if len(per_chat) > MAX_MESSAGES_PER_CHAT:
                    per_chat[:] = per_chat[-MAX_MESSAGES_PER_CHAT:]

            self._persist_state_locked()

        await self._emit_raw(
            {
                "type": "update",
                "source": "tg_message",
                "update": {"chat_id": cid, "message": msg_obj},
            }
        )

    async def _ptb_error_handler(
        self, update: object | None, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        err = getattr(ctx, "error", None) or Exception("unknown error")
        logger.exception("telegram handler error", exc_info=err)

        # Tell the system we're down; reconnect loop (if present) will attempt again.
        if self._is_transient_network_exc(err):
            with contextlib.suppress(Exception):
                await self._emit_raw(
                    {"type": "status", "status": "disconnected", "error": str(err)}
                )
            # If PTB doesn't automatically call handlers after disconnect, reconnect loop must be already running.
        else:
            with contextlib.suppress(Exception):
                await self._emit_raw({"type": "error", "error": str(err)})

    # ---------------- Event publishing / batching ----------------

    async def _emit_raw(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        await self._raw_q.put(event)

    def _ensure_zmq_publisher(self) -> None:
        if not self._zmq_pub_endpoint:
            return
        if self._zmq_publisher is not None:
            return

        topics = ZmqTopics(
            job=str(ZmqTopics.job),
            token=str(ZmqTopics.token),
            result=str(ZmqTopics.result),
            error=str(ZmqTopics.error),
            update_batch=str(ZmqTopics.update_batch),
        )

        self._zmq_publisher = ZmqPublisher(
            pub_endpoint=str(self._zmq_pub_endpoint),
            topics=topics,
            linger_ms=int(self.params.get("zmq_linger_ms", 0)),
            send_timeout_ms=int(self.params.get("zmq_send_timeout_ms", 5000)),
            slow_joiner_seconds=float(self.params.get("zmq_slow_joiner_seconds", 0.5)),
        )

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

                batch = {
                    "type": "update_batch",
                    "update": out_update,
                    "status": out_status,
                    "error": out_error,
                }

                # publish updates to ZMQ ONLY for incoming TG messages only
                logger_topic = None
                try:
                    if raw.get("source") == "tg_message":
                        self._ensure_zmq_publisher()
                        if self._zmq_publisher is not None:
                            logger_topic = self._zmq_publisher.topics.update_batch
                            self._zmq_publisher.publish_update_batch(batch)
                except Exception:
                    logger.exception("Failed to publish update_batch to ZMQ")

                logger.info(
                    "TelegramBotPoller: new incoming message, endpoint=%s, topic=%s",
                    self._zmq_pub_endpoint,
                    logger_topic,
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

        except Exception as exc:
            try:
                await app.shutdown()
            except Exception:
                pass

            with self._lock:
                self._ptb_started = False
                self._start_refcount = max(0, self._start_refcount - 1)

            # Ensure reconnect loop runs, but never crash the service
            with self._lock:
                if self._reconnect_task is None or self._reconnect_task.done():
                    self._stop_requested = False
                    self._reconnect_task = asyncio.create_task(self._reconnect_loop())

            status = (
                "reconnecting"
                if self._is_transient_network_exc(exc)
                else "reconnecting_after_error"
            )

            logger.warning("failed to start ptb app (%s): %s", status, str(exc))

            with contextlib.suppress(Exception):
                await self._emit_raw(
                    {"type": "status", "status": status, "error": str(exc)}
                )

            return {"type": "status", "status": status, "error": str(exc)}

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
        with self._lock:
            if getattr(self, "_instance_lock_acquired", False):
                # If already acquired, just make sure polling/reconnect is running.
                return await self._start_if_needed()
            self._instance_lock_acquired = True

        try:
            self._instance_lock.acquire()
        except RuntimeError as e:
            pid = None
            m = re.search(r"pid=(\d+)", str(e))
            if m:
                pid = int(m.group(1))

            with self._lock:
                self._instance_lock_acquired = False
            return {
                "type": "status",
                "status": "already_running",
                "pid": pid,
                "error": str(e),
            }

        self._register_signal_handlers()

        try:
            try:
                res = await self._start_if_needed()
                return res
            except Exception as exc:
                # Automatic forever reconnect: never crash start on network drop
                with self._lock:
                    self._ptb_started = False
                    if self._reconnect_task is None or self._reconnect_task.done():
                        self._stop_requested = False
                        self._reconnect_task = asyncio.create_task(
                            self._reconnect_loop()
                        )

                with contextlib.suppress(Exception):
                    await self._emit_raw(
                        {
                            "type": "status",
                            "status": "reconnecting",
                            "error": str(exc),
                            "transient": bool(self._is_transient_network_exc(exc)),
                        }
                    )
                return {"type": "status", "status": "reconnecting", "error": str(exc)}

        except Exception:
            # Ensure we don't leave the instance lock held on truly fatal failures
            self._maybe_release_lock()
            raise

    async def stop(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            if not self._ptb_started and not getattr(
                self, "_instance_lock_acquired", False
            ):
                # nothing running and we don't own anything
                return {"type": "status", "status": "not_started"}

            if not self._ptb_started and not force:
                # keep existing refcount semantics
                self._start_refcount = max(0, self._start_refcount - 1)
                if self._start_refcount > 0:
                    return {
                        "type": "status",
                        "status": "stop_deferred",
                        "refcount": self._start_refcount,
                    }

            self._start_refcount = 0 if force else max(0, self._start_refcount - 1)
            should_shutdown = force or self._start_refcount == 0

            # mark closed immediately to stop new work
            if should_shutdown:
                self._closed = True

        if not should_shutdown:
            return {"type": "status", "status": "stop_deferred"}

        # prevent any future reconnect attempts while shutting down
        self._stop_requested = True

        # Cancel reconnect task and await it
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            with contextlib.suppress(Exception):
                await self._reconnect_task

        # Cancel batcher task if present
        batch_task = None
        with self._lock:
            batch_task = self._batch_task
        if batch_task is not None:
            batch_task.cancel()
            with contextlib.suppress(Exception):
                await batch_task

        # Signal any waiting queues to end
        with contextlib.suppress(Exception):
            await self._raw_q.put(None)
        with contextlib.suppress(Exception):
            await self._event_q.put(None)

        # Stop PTB app cleanly if it was started
        app = self._ptb_app
        if app is not None:
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

        # Release lock only if we own it
        should_release = False
        with self._lock:
            should_release = getattr(self, "_instance_lock_acquired", False)
            self._instance_lock_acquired = False
            self._closed = True

        if should_release:
            with contextlib.suppress(Exception):
                self._instance_lock.release()

        return {"type": "status", "status": "stopped"}

    # ---------------- Operations  ----------------

    async def get_unread(self) -> Dict[str, Any]:
        mark_read = _param_bool(self.params.get("mark_read"), default=True)

        # Always refresh from disk before computing unread
        with self._lock:
            self._state = self._load_state_from_disk_locked()
            messages_by_chat = self._state.get("messages_by_chat_id", {}) or {}
            last_read_by_chat = self._state.get("last_read_by_chat_id", {}) or {}

            # Unblock only when we see a message with date > blocked_at
            try:
                self._load_blacklist_locked()
                key = self._bot_account_key()
                blacklisted_map = self._blacklist.get(key, {}) or {}  # {chat_id_s: blocked_epoch_s}

                for chat_id_s, blocked_epoch_s in blacklisted_map.items():
                    if chat_id_s not in messages_by_chat.keys():
                        continue

                    should_unblock = False
                    for m in messages_by_chat.get(chat_id_s, []) or []:
                        if not isinstance(m, dict):
                            continue
                        msg_date = m.get("date")
                        try:
                            if msg_date is not None and int(msg_date) > int(blocked_epoch_s):
                                should_unblock = True
                                break
                        except Exception:
                            continue

                    if should_unblock:
                        self._remove_chat_from_blacklist_locked(chat_id_s)
            except Exception:
                logger.exception("Failed while handling tg_black_list.json during get_unread")

            # Work on computed copies for payload; update _state later if needed
            messages_by_chat_items = {k: list(v) for k, v in messages_by_chat.items()}
            last_read_copy = dict(last_read_by_chat)

        chats: List[Dict[str, Any]] = []
        updates_to_apply: List[Tuple[str, int]] = []

        for chat_key, messages in messages_by_chat_items.items():
            try:
                cid = int(chat_key)
            except Exception:
                continue

            try:
                lr = int(last_read_copy.get(chat_key, 0) or 0)
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

        payload = {"chats": chats, "last_read": last_read_copy}

        if mark_read and updates_to_apply:
            with self._lock:
                # Re-load again to prevent overwriting concurrent updates
                self._state = self._load_state_from_disk_locked()

                # Apply only to chat keys that exist in messages_by_chat_id (robust to missing chats)
                msgs = self._state.get("messages_by_chat_id", {}) or {}
                for chat_key, new_lr in updates_to_apply:
                    if chat_key in msgs:
                        self._state["last_read_by_chat_id"][chat_key] = new_lr

                self._persist_state_locked()

                # update payload last_read to match what we wrote
                last_read_copy = dict(self._state.get("last_read_by_chat_id", {}) or {})
                payload["last_read"] = last_read_copy

        logger.info("TelegramBotPoller: get_unread requested")
        await self._emit_raw(
            {"type": "update", "source": "get_unread", "update": payload}
        )

        return {"type": "update", "update": payload}


    async def send_message(
        self,
        chat_id: int | str,
        message: Any,
        *,
        wait_for_delivery: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if not getattr(self, "_instance_lock_acquired", False):
            raise RuntimeError(
                "TelegramBotPoller instance lock not held (not the active instance)"
            )

        with self._lock:
            if not self._ptb_started:
                raise RuntimeError("bot not started; call await start() first")
            if self._closed:
                raise RuntimeError("poller is stopping/closed")

        # Refuse to send to blacklisted chats for this bot account
        with self._lock:
            try:
                if self._is_chat_blacklisted_locked(chat_id):
                    return {
                        "type": "error",
                        "error": {
                            "error": "blacklisted",
                            "chat_id": chat_id,
                        },
                    }
            except Exception:
                # If blacklist file is broken/unreadable, fall through to normal send
                pass

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
        else:
            # since chat_id is typed as int|str, only str remains here
            send_target = int(chat_id) if chat_id.isdigit() else chat_id

        try:
            sent: Message = await bot.send_message(
                chat_id=send_target,
                text=str(message),
            )
        except Forbidden as exc:
            forbidden_result_update: Dict[str, Any] = {
                "error": "forbidden",
                "telegram_error": "Forbidden",
                "detail": str(exc),
                "chat_id": chat_id,
                "blocked_or_removed": True,
            }
            await self._emit_raw({"type": "error", "update": forbidden_result_update})

            # On forbidden: blocklist this chat for this bot account
            with self._lock:
                self._add_chat_to_blacklist_locked(chat_id)

            return {"type": "error", "error": forbidden_result_update}

        msg_shape = _normalize_message_to_tdlib_shape(sent)

        cid = msg_shape.get("chat_id")
        msg_obj = msg_shape.get("message") or {}
        msg_id = msg_obj.get("id") if isinstance(msg_obj, dict) else None

        if cid is not None and isinstance(msg_obj, dict) and msg_obj:
            chat_key = str(int(cid))

            with self._lock:
                self._state = self._load_state_from_disk_locked()
                per_chat = self._state["messages_by_chat_id"].setdefault(chat_key, [])

                existing_ids = {
                    m.get("id")
                    for m in per_chat
                    if isinstance(m, dict) and m.get("id") is not None
                }

                if msg_id is None or msg_id not in existing_ids:
                    per_chat.append(msg_obj)

                def msg_sort_key(m: Any) -> int:
                    if not isinstance(m, dict):
                        return -1
                    v = m.get("id")
                    try:
                        return int(v) if v is not None else -1
                    except Exception:
                        return -1

                try:
                    per_chat.sort(key=msg_sort_key)
                except Exception:
                    pass

                if len(per_chat) > MAX_MESSAGES_PER_CHAT:
                    per_chat[:] = per_chat[-MAX_MESSAGES_PER_CHAT:]

                # mark sent message as read after successful send
                if msg_id is not None:
                    try:
                        self._state["last_read_by_chat_id"][chat_key] = int(msg_id)
                    except Exception:
                        pass

                self._persist_state_locked()

        result_update: Dict[str, Any] = {"message": msg_shape.get("message")}
        if wait_for_delivery:
            result_update["delivered"] = True
            result_update["new_message_id"] = msg_id

        await self._emit_raw({"type": "update", "update": result_update})
        return {"type": "update", "update": result_update}

    async def raw(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        self._require_instance_owner()

        with self._lock:
            if not self._ptb_started:
                raise RuntimeError("bot not started; call await start() first")
            if self._closed:
                raise RuntimeError("poller is stopping/closed")

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
