import asyncio
import atexit
import fcntl
import inspect
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.tools import get_tool_workflow_path
from gui.chat.turn_driver import create_session, handle_turn
from gui.components.settings import get_telegram_enabled_option
from messengers_integrations.telegram.telegram_bot_api.tg_zmq_subscriber import (
    TgZmqSubscriberService,
)
from runtime.run import run_workflow

from .tg_update_subscriber import TgUpdateSubscriber

# We have to ensure the telegram service is started to get updates from
_tg_subscriber_service: Optional[TgZmqSubscriberService] = None

# Config
UPDATE_INTERVAL_S = 60
GET_CHATS_FOLLOW_UP_USER_MESSAGE = (
    "You have new unread messages to handle. Check the unread messages."
)
MESSENGER = "telegram"
MAX_WORKERS = 2
DEFAULT_MAX_CONCURRENCY: int = 8

_LOCK_PATH = "/tmp/telegram_get_unread_poller.lock"
_fd: Optional[int] = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("get_chats_poller")

_cached_workflow_paths: dict[str, Path] = {}
_EXECUTOR: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(MAX_WORKERS)


def get_cached_workflow_path(tool_id: str) -> Path:
    p = _cached_workflow_paths.get(tool_id)
    if not p:
        p = get_tool_workflow_path(tool_id)
        _cached_workflow_paths[tool_id] = p
    return p


def _log_tg_get_unread_error(outputs_dict: Dict[str, Any]) -> None:
    for unit_id, unit_val in outputs_dict.items():
        if not isinstance(unit_val, dict):
            continue
        if unit_id == "tg_get_unread" or unit_val.get("name") == "tg_get_unread":
            port_error = None
            if isinstance(unit_val.get("outputs"), dict):
                port_error = unit_val["outputs"].get("error") or unit_val[
                    "outputs"
                ].get("2")
            port_error = port_error or unit_val.get("error") or unit_val.get("2")
            if port_error:
                logger.error("tg_get_unread unit error port: %s", port_error)
        for k, v in unit_val.items():
            if isinstance(v, dict):
                _log_tg_get_unread_error({k: v})


def _extract_updates(outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    if not isinstance(outputs, dict):
        return updates

    # CASE: workflow returned the inner payload directly
    # e.g. {"chats": [...], "last_read": {...}}
    if isinstance(outputs.get("chats"), list) or outputs.get("last_read") is not None:
        return [{"type": "update", "update": outputs}]

    for v in outputs.values():
        if isinstance(v, dict) and v.get("type") == "update" and "update" in v:
            u = v.get("update")
            if isinstance(u, list):
                updates.extend([item for item in u if isinstance(item, dict)])
            elif isinstance(u, dict):
                updates.append(u)

    direct = outputs.get("update")
    if (
        isinstance(direct, dict)
        and direct.get("type") == "update"
        and "update" in direct
    ):
        u = direct.get("update")
        if isinstance(u, list):
            updates.extend([item for item in u if isinstance(item, dict)])
        elif isinstance(u, dict):
            updates.append(u)

    return updates


def _update_has_unread_and_session(update: Dict[str, Any]) -> Optional[str]:
    def find_chats(obj: Any) -> Optional[List[Dict[str, Any]]]:
        if isinstance(obj, dict):
            chats = obj.get("chats")
            if (
                isinstance(chats, list)
                and chats
                and all(isinstance(x, dict) for x in chats)
            ):
                return chats
            for v in obj.values():
                res = find_chats(v)
                if res is not None:
                    return res
        elif isinstance(obj, list):
            for it in obj:
                res = find_chats(it)
                if res is not None:
                    return res
        return None

    if not isinstance(update, dict):
        return None

    inner = update.get("update") if isinstance(update.get("update"), dict) else update
    chats = find_chats(inner)
    if not isinstance(chats, list) or not chats:
        return None

    # If unread_count exists, ensure it's >0; otherwise just act on presence
    first = chats[0]
    if isinstance(first, dict):
        unread_count = first.get("unread_count")
        if unread_count is not None and int(unread_count) <= 0:
            return None

        sid = (
            first.get("session_id")
            or first.get("chat_id")
            or first.get("id")
            or first.get("peer_id")
        )
        return str(sid) if sid is not None else None

    return None


async def _safe_handle_turn(sess: str) -> None:
    try:
        logger.info("telegram_worker: session=%s: triggering handle_turn()", sess)
        outputs = await handle_turn(sess, GET_CHATS_FOLLOW_UP_USER_MESSAGE, MESSENGER)
    except Exception:
        logger.exception("session=%s: handle_turn exception", sess)
        return

    if outputs is None:
        logger.warning("session=%s: handle_turn returned None", sess)
        return

    ok = True
    out_session = sess
    msg = outputs.get("message") if isinstance(outputs, dict) else None
    if isinstance(msg, dict) and msg.get("session_id"):
        out_session = msg.get("session_id")

    out_messenger = outputs.get("messenger") if isinstance(outputs, dict) else None
    out_messenger = out_messenger or MESSENGER
    if out_messenger != MESSENGER:
        logger.error(
            "session=%s: messenger mismatch expected=%s got=%s",
            sess,
            MESSENGER,
            out_messenger,
        )
        ok = False

    if not out_session:
        logger.error("session=%s: missing session id in outputs", sess)
        ok = False

    if ok:
        logger.info("session=%s: handled unread messages successfully", out_session)
    else:
        logger.warning("session=%s: handled with verification issues", sess)


async def _run_get_chats_single_sync(
    workflow_path: Path, inject_payload: Dict[str, Any]
) -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        return (
            run_workflow(
                workflow_path,
                initial_inputs={"inject_get_unread": {"data": inject_payload}},
                format="dict",
            )
            or {}
        )

    loop = asyncio.get_running_loop()
    outputs = await loop.run_in_executor(_EXECUTOR, _run)
    try:
        _log_tg_get_unread_error(outputs)
    except Exception:
        logger.exception("Error while inspecting unit outputs for tg_get_unread")
    return outputs


class GetChatsPoller:
    """
    Periodically runs the get_chats workflow and triggers turns when unread updates are present.

    Also supports extra runs triggered by TgUpdateSubscriber via run_once_from_trigger().
    """

    def __init__(
        self,
        interval_s: int = UPDATE_INTERVAL_S,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ):
        self.interval_s = interval_s
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._sem = asyncio.Semaphore(max_concurrency)

        # uses zmq update subscriber as an additional trigger for the loop
        self._subscriber = TgUpdateSubscriber(self)

        # protects against overlapping run_once invocations if you get bursty ZMQ
        self._run_once_lock = asyncio.Lock()

    async def _handle_update_event(self, update_event: dict[str, Any]) -> None:
        logger.info(
            "_handle_update_event CALLED: keys=%s raw_type=%s",
            list(update_event.keys()) if isinstance(update_event, dict) else None,
            type(update_event.get("update"))
            if isinstance(update_event, dict)
            else None,
        )

        raw = update_event.get("update")
        if isinstance(raw, list):
            updates = [u for u in raw if isinstance(u, dict)]
        elif isinstance(raw, dict):
            updates = [raw]
        else:
            updates = []

        logger.info(
            "_handle_update_event: raw_list_len=%s updates_count=%s sample_item_type=%s",
            len(raw) if isinstance(raw, list) else None,
            len(updates),
            type(raw[0]) if isinstance(raw, list) and raw else None,
        )

        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            logger.info(
                "_handle_update_event: raw[0] keys=%s",
                list(raw[0].keys()),
            )

        for u in updates:
            logger.info(
                "_handle_update_event: update_item keys=%s",
                list(u.keys()) if isinstance(u, dict) else None,
            )
            logger.info("u=%s", u)
            sess = _update_has_unread_and_session(u)
            logger.info("handle_update_event: computed sess=%s", sess)
            if not sess:
                continue
            sess = create_session(sess)
            logger.info("session=%s: unread detected; invoking handle_turn", sess)
            async with self._sem:
                await _safe_handle_turn(sess)

    async def _run_workflow_and_handle(self) -> None:
        workflow_path = get_cached_workflow_path("get_chats")
        inject_payload = {"action": "get_unread", "messenger": MESSENGER}

        try:
            outputs = await _run_get_chats_single_sync(workflow_path, inject_payload)
            status = "ok"
            error_msg = None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            outputs = {}
            status = "error"
            error_msg = str(e)
            logger.exception("poll run error")

        # Force a single update item containing the workflow output
        # (handle_update_event will iterate 1 item, not 0).
        update_items: list[dict[str, Any]] = [{"type": "update", "update": outputs}]

        await self._handle_update_event(
            {
                "type": "update_batch",
                "update": update_items,
                "status": status,
                "error": error_msg,
            }
        )

    async def run_once_from_trigger(self, _zmq_event: dict[str, Any]) -> None:
        """
        Extra run requested by the ZMQ subscriber.
        Runs a single workflow cycle and handles any unread turns.
        """
        logger.info(
            "run_once_from_trigger CALLED: keys=%s",
            list(_zmq_event.keys())
            if isinstance(_zmq_event, dict)
            else type(_zmq_event),
        )
        async with self._run_once_lock:
            # You asked: "When an update is received via zmq, it will run an additional GetChatsPoller._loop()."
            # Since _loop is periodic, we interpret this as "one extra cycle". This method is that cycle.
            await self._run_workflow_and_handle()

    async def _loop(self) -> None:
        logger.info("GetChatsPoller started")

        try:
            while not self._stop.is_set():
                await self._run_workflow_and_handle()
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("GetChatsPoller stopping")

    def start(self) -> None:
        if self._task and not self._task.done():
            logger.warning("poller already running")
            return
        self._stop.clear()

        # Start subscriber alongside periodic loop
        self._subscriber.start()

        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        await self._subscriber.stop()

        t = getattr(self, "_task", None)
        if isinstance(t, asyncio.Task) and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass


_poller: Optional[GetChatsPoller] = None


async def _start_telegram_poller() -> tuple[bool, str]:
    global _poller, _tg_subscriber_service, _fd

    # already running?
    if _poller is not None or _tg_subscriber_service is not None:
        return True, "already"

    if not get_telegram_enabled_option():
        return False, "disabled"

    # lock (same as your existing code)
    try:
        _fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR)
        fcntl.flock(_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False, "another instance is already running (lock) "

    # Start order: TgZmqSubscriberService first, then GetChatsPoller
    try:
        _tg_subscriber_service = TgZmqSubscriberService()
        logger.info("Telegram tg_zmq subscriber starting.")
        _tg_subscriber_service.start()
        logger.info("Telegram tg_zmq subscriber started.")

        _poller = GetChatsPoller(
            interval_s=UPDATE_INTERVAL_S,
            max_concurrency=DEFAULT_MAX_CONCURRENCY,
        )
        logger.info("Telegram get_chats poller starting.")
        _poller.start()
        logger.info("Telegram get_chats poller started.")

        return True, "started"
    except Exception as e:
        logger.exception("Failed to start Telegram pollers")

        # best-effort cleanup in reverse order
        try:
            if _poller is not None:
                await _poller.stop()
        except Exception:
            logger.exception("Failed to stop GetChatsPoller during startup failure")

        try:
            if _tg_subscriber_service is not None:
                await _tg_subscriber_service.stop()
        except Exception:
            logger.exception(
                "Failed to stop TgZmqSubscriberService during startup failure"
            )

        _poller = None
        _tg_subscriber_service = None
        try:
            if _fd is not None:
                os.close(_fd)
        except Exception:
            pass
        _fd = None

        return False, str(e)


def _stop_telegram_poller_on_exit() -> None:
    global _poller, _tg_subscriber_service, _EXECUTOR, _fd

    # helper to stop either sync or async stop_fn
    async def _maybe_stop_async(stop_fn) -> None:
        if stop_fn is None:
            return
        maybe = stop_fn()
        if inspect.iscoroutine(maybe):
            await maybe

    try:
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except Exception:
                loop = None

        # stop GetChatsPoller
        stop_fn = getattr(_poller, "stop", None)
        if _poller is not None and stop_fn is not None:
            if loop and loop.is_running():
                if inspect.iscoroutinefunction(stop_fn):
                    asyncio.run_coroutine_threadsafe(stop_fn(), loop).result(
                        timeout=3.0
                    )
                else:
                    maybe = stop_fn()
                    if asyncio.iscoroutine(maybe):
                        asyncio.run_coroutine_threadsafe(maybe, loop).result(
                            timeout=3.0
                        )
            else:
                # during interpreter shutdown, avoid blocking
                if inspect.iscoroutinefunction(stop_fn):
                    logger.warning(
                        "Cannot await GetChatsPoller.stop() during interpreter shutdown"
                    )
                else:
                    maybe = stop_fn()
                    if asyncio.iscoroutine(maybe):
                        logger.warning(
                            "Cannot await GetChatsPoller.stop() during interpreter shutdown"
                        )

        # stop TgZmqSubscriberService
        stop_fn2 = getattr(_tg_subscriber_service, "stop", None)
        if _tg_subscriber_service is not None and stop_fn2 is not None:
            if loop and loop.is_running():
                if inspect.iscoroutinefunction(stop_fn2):
                    asyncio.run_coroutine_threadsafe(stop_fn2(), loop).result(
                        timeout=3.0
                    )
                else:
                    maybe = stop_fn2()
                    if asyncio.iscoroutine(maybe):
                        asyncio.run_coroutine_threadsafe(maybe, loop).result(
                            timeout=3.0
                        )
            else:
                if inspect.iscoroutinefunction(stop_fn2):
                    logger.warning(
                        "Cannot await TgZmqSubscriberService.stop() during interpreter shutdown"
                    )
                else:
                    maybe = stop_fn2()
                    if asyncio.iscoroutine(maybe):
                        logger.warning(
                            "Cannot await TgZmqSubscriberService.stop() during interpreter shutdown"
                        )

    except Exception:
        logger.exception("Error stopping Telegram pollers")
    finally:
        _poller = None
        _tg_subscriber_service = None

        try:
            if _fd is not None:
                os.close(_fd)
        except Exception:
            pass
        _fd = None

        try:
            if _EXECUTOR is not None:
                _EXECUTOR.shutdown(wait=False)
        except Exception:
            logger.exception("Error shutting down thread executor")


atexit.register(_stop_telegram_poller_on_exit)
