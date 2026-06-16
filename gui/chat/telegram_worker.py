import asyncio
import atexit
import inspect
import logging
import threading
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


def get_cached_workflow_path(tool_id: str) -> Path:
    p = _cached_workflow_paths.get(tool_id)
    if not p:
        p = get_tool_workflow_path(tool_id)
        _cached_workflow_paths[tool_id] = p
    return p


# Run the get_chats workflow in a thread and return outputs (dict)
def _run_get_chats_sync(
    workflow_path: Path, inject_payload: Dict[str, Any]
) -> Dict[str, Any]:
    try:
        outputs = (
            run_workflow(
                workflow_path,
                initial_inputs={"inject_get_unread": {"data": inject_payload}},
                format="dict",
            )
            or {}
        )

        # Log tg_get_unread unit's error output (port 2 / named "error")
        def _log_tg_get_unread_error(outputs_dict: Dict[str, Any]) -> None:
            for unit_id, unit_val in outputs_dict.items():
                if not isinstance(unit_val, dict):
                    continue
                # Match the unit by id/name; adjust "tg_get_unread" if your unit id differs
                if (
                    unit_id == "tg_get_unread"
                    or unit_val.get("name") == "tg_get_unread"
                ):
                    # common shapes: outputs under "outputs" or direct keys
                    port_error = None
                    if isinstance(unit_val.get("outputs"), dict):
                        # try named "error" first, then numeric key "2"
                        port_error = unit_val["outputs"].get("error") or unit_val[
                            "outputs"
                        ].get("2")
                    port_error = (
                        port_error or unit_val.get("error") or unit_val.get("2")
                    )
                    if port_error:
                        logger.error("tg_get_unread unit error port: %s", port_error)
                # recurse into nested dicts if present
                for k, v in unit_val.items():
                    if isinstance(v, dict):
                        _log_tg_get_unread_error({k: v})

        try:
            _log_tg_get_unread_error(outputs)
        except Exception:
            logger.exception("Error while inspecting unit outputs for tg_get_unread")

        return outputs
    except Exception:
        raise


async def run_get_chats_workflow() -> Dict[str, Any]:
    # payload per Telegram unit input API
    inject_payload = {"action": "get_unread", "messenger": MESSENGER}
    workflow_path = get_cached_workflow_path("get_chats")
    return await asyncio.to_thread(_run_get_chats_sync, workflow_path, inject_payload)


# Extract telegram updates from workflow outputs.
def _extract_updates(outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    if not isinstance(outputs, dict):
        return updates
    # Common run_workflow shape: unit outputs available under keys; search for 'update' or unit id outputs
    for v in outputs.values():
        if isinstance(v, dict) and v.get("type") == "update" and "update" in v:
            u = v.get("update")
            if isinstance(u, list):
                updates.extend([item for item in u if isinstance(item, dict)])
            elif isinstance(u, dict):
                updates.append(u)
    # Also check direct 'update' key
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


# Determine if an update indicates unread messages and extract a session/chat id
def _update_has_unread_and_session(update: Dict[str, Any]) -> Optional[str]:
    # TelegramClient update shape is implementation-dependent. Heuristics:
    # - If update contains 'unread' or 'unread_count' or 'messages' list -> consider unread
    # - Use 'chat_id' or 'chat' or 'from' / 'peer_id' to derive session id
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

    # session id heuristics
    session_id = update.get("session_id") or update.get("chat_id") or None
    # try nested paths
    if session_id is None:
        msg = update.get("message") or update.get("update") or {}
        if isinstance(msg, dict):
            session_id = (
                msg.get("chat_id")
                or msg.get("peer_id")
                or msg.get("from", {}).get("id")
            )
    if session_id is None:
        # fallback: generate/let turn_driver create one (return None to indicate creation)
        return None
    return str(session_id)


class GetChatsPoller:
    def __init__(self, interval_s: int = UPDATE_INTERVAL_S):
        self.interval_s = interval_s
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def _handle_update(self, update: Dict[str, Any]) -> None:
        sess = _update_has_unread_and_session(update)
        sess = create_session(sess)  # creates if None
        logger.info("session=%s: unread detected; invoking handle_turn", sess)
        try:
            outputs = await handle_turn(
                sess, GET_CHATS_FOLLOW_UP_USER_MESSAGE, MESSENGER
            )
        except Exception as e:
            logger.exception("session=%s: handle_turn exception: %s", sess, e)
            return

        if outputs is None:
            logger.warning("session=%s: handle_turn returned None", sess)
            return

        # Verification
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
                    await asyncio.gather(*tasks)
                else:
                    logger.debug("no updates / no unread found")
            except Exception as e:
                logger.exception("polling error: %s", e)

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
            # schedule the loop coroutine
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

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task


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
        _poller.start()  # now there is a running loop
        logger.info("Telegram poller started.")
        return True, "started"
    except Exception as e:
        logger.exception("Failed to start Telegram poller")
        _poller = None
        return False, str(e)


def _stop_telegram_poller_on_exit() -> None:
    global _poller
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
            # no running loop in this thread; try the default loop
            try:
                loop = asyncio.get_event_loop()
            except Exception:
                loop = None

        if loop and loop.is_running():
            # schedule coroutine on existing loop
            if inspect.iscoroutinefunction(stop_fn):
                asyncio.run_coroutine_threadsafe(stop_fn(), loop).result(timeout=3.0)
            else:
                maybe = stop_fn()
                if asyncio.iscoroutine(maybe):
                    asyncio.run_coroutine_threadsafe(maybe, loop).result(timeout=3.0)
        else:
            # fallback: call sync stop if available (should not call asyncio.run here)
            if not inspect.iscoroutinefunction(stop_fn):
                maybe = stop_fn()
                if asyncio.iscoroutine(maybe):
                    # can't await it safely here; log and skip
                    logger.warning(
                        "Cannot await stop coroutine during interpreter shutdown"
                    )
    except Exception:
        logger.exception("Error stopping Telegram poller")
    finally:
        _poller = None


def _cancel_task(task: asyncio.Task) -> None:
    try:
        task.cancel()
    except Exception:
        pass


async def _run_stop_coroutine(stop_coro_or_fn):
    """
    stop_coro_or_fn: either an awaitable (coroutine) or a zero-arg callable returning one.
    """
    # obtain coroutine object
    if callable(stop_coro_or_fn):
        try:
            maybe = stop_coro_or_fn()
        except Exception:
            logger.exception("Error calling stop function")
            return
    else:
        maybe = stop_coro_or_fn

    # ensure it's awaitable
    if not asyncio.iscoroutine(maybe) and not isinstance(maybe, asyncio.Future):
        logger.warning("stop did not return a coroutine; nothing to await")
        return

    coro = maybe

    # cancel internal task first
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

    # now await the stop coroutine and handle CancelledError gracefully
    try:
        await coro
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Exception while awaiting poller.stop()")


# register Telegram poller stopper
atexit.register(_stop_telegram_poller_on_exit)


# Example startup
# async def main():
#    # check telegram enabled before starting poller
#    if not get_telegram_enabled_option():
#        logger.info("Telegram integration is disabled; poller will not start.")
#        try:
#            # keep process alive (optional) or exit immediately
#                await asyncio.sleep(3600)
#        except (asyncio.CancelledError, KeyboardInterrupt):
#            logger.info("shutdown requested")
#        return
#
#    poller = GetChatsPoller()
#    logger.info("Telegram poller starting.")
#    poller.start()
#    logger.info("Telegram poller started.")
#    try:
#        while True:
#            await asyncio.sleep(3600)
#    except (asyncio.CancelledError, KeyboardInterrupt):
#        logger.info("shutdown requested")
#    finally:
#        await poller.stop()
#
#
# if __name__ == "__main__":
#     asyncio.run(main())
