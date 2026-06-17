import asyncio
import atexit
import inspect
import logging
import threading
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.tools import get_tool_workflow_path
from gui.chat.turn_driver import create_session, handle_turn
from gui.components.settings import get_telegram_enabled_option
from runtime.run import run_workflow

# Config
UPDATE_INTERVAL_S = 60
GET_CHATS_FOLLOW_UP_USER_MESSAGE = (
    "You have new unread messages to handle. Check the unread messages."
)
MESSENGER = "telegram"

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("get_chats_poller")

# Cache workflow path to prevent fetching it every poll
_cached_workflow_paths: dict[str, Path] = {}

# Module-level ProcessPoolExecutor for CPU-bound workflow runs
_PROCESS_POOL: Optional[ProcessPoolExecutor] = ProcessPoolExecutor(max_workers=2)


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


def _run_get_chats_sync(
    workflow_path: Path, inject_payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Synchronous wrapper that will be executed in a process worker.
    Keep this function sync to avoid pickling issues with run_workflow.
    """
    try:
        outputs = (
            run_workflow(
                workflow_path,
                initial_inputs={"inject_get_unread": {"data": inject_payload}},
                format="dict",
            )
            or {}
        )
        try:
            _log_tg_get_unread_error(outputs)
        except Exception:
            logger.exception("Error while inspecting unit outputs for tg_get_unread")
        return outputs
    except Exception:
        raise


async def run_get_chats_workflow() -> Dict[str, Any]:
    inject_payload = {"action": "get_unread", "messenger": MESSENGER}
    workflow_path = get_cached_workflow_path("get_chats")
    loop = asyncio.get_running_loop()
    # Run in process pool to avoid GIL/CPU blocking inside run_workflow
    try:
        return await loop.run_in_executor(
            _PROCESS_POOL, _run_get_chats_sync, workflow_path, inject_payload
        )
    except Exception:
        raise


def _extract_updates(outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    if not isinstance(outputs, dict):
        return updates
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
    unread = None
    if "unread" in update:
        unread = update.get("unread")
    elif "unread_count" in update:
        unread = update.get("unread_count")
    elif (
        "messages" in update
        and isinstance(update.get("messages"), list)
        and update.get("messages")
    ):
        unread = True
    elif update.get("type") == "update" and update.get("update", {}).get("message"):
        unread = True

    if not unread:
        return None

    session_id = update.get("session_id") or update.get("chat_id") or None
    if session_id is None:
        msg = update.get("message") or update.get("update") or {}
        if isinstance(msg, dict):
            session_id = (
                msg.get("chat_id")
                or msg.get("peer_id")
                or msg.get("from", {}).get("id")
            )
    if session_id is None:
        return None
    return str(session_id)


async def _safe_handle_turn(sess: str) -> None:
    """
    Wrap handle_turn to isolate exceptions and bound per-update concurrency.
    """
    try:
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
    out_messenger = outputs.get("messenger") or MESSENGER
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


class GetChatsPoller:
    def __init__(self, interval_s: int = UPDATE_INTERVAL_S, max_concurrency: int = 8):
        self.interval_s = interval_s
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        # semaphore to bound concurrent handle_turn calls
        self._sem = asyncio.Semaphore(max_concurrency)
        # internal flag to indicate running in a dedicated thread loop
        self._thread: Optional[threading.Thread] = None

    async def _handle_update(self, update: Dict[str, Any]) -> None:
        sess = _update_has_unread_and_session(update)
        sess = create_session(sess)  # creates if None
        logger.info("session=%s: unread detected; invoking handle_turn", sess)
        # bound concurrency per poller
        async with self._sem:
            await _safe_handle_turn(sess)

    async def _loop(self) -> None:
        logger.info("GetChatsPoller started (interval=%s)", self.interval_s)
        while not self._stop.is_set():
            try:
                raw_outputs = await run_get_chats_workflow()
                updates = _extract_updates(raw_outputs)
                if updates:
                    tasks = [
                        asyncio.create_task(self._handle_update(u)) for u in updates
                    ]
                    # gather but don't let one failing update stop others
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, Exception):
                            logger.exception("update handler exception: %s", r)
                else:
                    logger.debug("no updates / no unread found")
            except Exception:
                logger.exception("polling error")

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                continue
        logger.info("GetChatsPoller stopped")

    def start(self) -> None:
        if self._task and not self._task.done():
            logger.warning("poller already running")
            return
        self._stop.clear()
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._loop())
        except RuntimeError:
            # no running loop in this thread: create a dedicated thread+loop for poller
            def _thread_target():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._task = loop.create_task(self._loop())
                try:
                    loop.run_until_complete(self._task)
                finally:
                    pending = asyncio.all_tasks(loop)
                    for t in pending:
                        t.cancel()
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.close()

            t = threading.Thread(target=_thread_target, daemon=True)
            t.start()
            self._thread = t

    async def stop(self) -> None:
        self._stop.set()
        # cancel the internal task to speed shutdown
        try:
            t = getattr(self, "_task", None)
            if isinstance(t, asyncio.Task) and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        except Exception:
            logger.exception("Error cancelling poller task")

        # If running in a dedicated thread, give it a moment to exit
        if self._thread and self._thread.is_alive():
            # nothing we can await here; thread will exit when loop completes
            self._thread.join(timeout=2.0)

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()


_poller: Optional[GetChatsPoller] = None


async def _start_telegram_poller() -> tuple[bool, str]:
    global _poller
    if _poller is not None:
        return True, "already"
    if not get_telegram_enabled_option():
        return False, "disabled"
    try:
        _poller = GetChatsPoller()
        logger.info("Telegram poller starting.")
        _poller.start()
        logger.info("Telegram poller started.")
        return True, "started"
    except Exception as e:
        logger.exception("Failed to start Telegram poller")
        _poller = None
        return False, str(e)


def _stop_telegram_poller_on_exit() -> None:
    global _poller, _PROCESS_POOL
    if _poller is None:
        return
    stop_fn = getattr(_poller, "stop", None)
    if stop_fn is None:
        return
    try:
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except Exception:
                loop = None

        if loop and loop.is_running():
            if inspect.iscoroutinefunction(stop_fn):
                asyncio.run_coroutine_threadsafe(stop_fn(), loop).result(timeout=3.0)
            else:
                maybe = stop_fn()
                if asyncio.iscoroutine(maybe):
                    asyncio.run_coroutine_threadsafe(maybe, loop).result(timeout=3.0)
        else:
            if not inspect.iscoroutinefunction(stop_fn):
                maybe = stop_fn()
                if asyncio.iscoroutine(maybe):
                    logger.warning(
                        "Cannot await stop coroutine during interpreter shutdown"
                    )
    except Exception:
        logger.exception("Error stopping Telegram poller")
    finally:
        _poller = None
        # shutdown process pool
        try:
            if _PROCESS_POOL is not None:
                _PROCESS_POOL.shutdown(wait=False)
        except Exception:
            logger.exception("Error shutting down process pool")


def _cancel_task(task: asyncio.Task) -> None:
    try:
        task.cancel()
    except Exception:
        pass


async def _run_stop_coroutine(stop_coro_or_fn):
    if callable(stop_coro_or_fn):
        try:
            maybe = stop_coro_or_fn()
        except Exception:
            logger.exception("Error calling stop function")
            return
    else:
        maybe = stop_coro_or_fn

    if not asyncio.iscoroutine(maybe) and not isinstance(maybe, asyncio.Future):
        logger.warning("stop did not return a coroutine; nothing to await")
        return

    coro = maybe

    try:
        t = getattr(_poller, "_task", None)
        if isinstance(t, asyncio.Task) and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    except Exception:
        logger.exception("Error cancelling poller task")

    try:
        await coro
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Exception while awaiting poller.stop()")


atexit.register(_stop_telegram_poller_on_exit)
