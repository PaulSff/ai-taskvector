"""
The resulting structure is:

AgenticLoopPoller
├── FollowupCtxSubscriber
└── AgenticTurnQueue
    └── worker tasks
        └── run_agentic_loop(...)

The poller should:

 -Start the queue.
- Start the subscriber.
- Receive subscriber events.
- Validate and submit jobs to the queue.
- Stop the subscriber first.
- Stop the queue afterward.
- Continue managing the process lock and global lifecycle state.

--
The subscriber payload should provide the session context, for example:
{
    "session_id": "chat-or-session-id",
    "unread_chats": [...],
}

or

{
    "session_id": "todo-list-id",
    "incomplete_tasks": [...],
}
"""
from __future__ import annotations

import asyncio
import atexit
import fcntl
import logging
import os
import signal
from typing import TypeGuard

from core.schemas import TodoTask
from gui.components.settings import get_telegram_enabled_option
from messengers_integrations import MessengerChatUpdate
from services.agentic_loop import cfg_helpers as cfg
from services.logging import setup_colored_logging

from .follow_up_ctx_subscriber import FollowupCtxSubscriber
from .queue import AgenticTurnQueue
from .update_to_agentic_jobs import (
    update_to_agentic_jobs,
)

MAX_CONCURRENCY = cfg.default_max_concurrency
QUEUE_SIZE = 100
_LOCK_PATH = cfg.lock_file_path

logger = setup_colored_logging(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

_fd: int | None = None
_poller: AgenticLoopPoller | None = None
_is_running = False
_stop_in_progress = False
_state_lock = asyncio.Lock()


def is_messenger_chat_update_list(
    value: object,
) -> TypeGuard[list[MessengerChatUpdate]]:
    return (
        isinstance(value, list)
        and all(isinstance(item, MessengerChatUpdate) for item in value)
    )

def is_incomplete_task_list(
    value: object,
) -> TypeGuard[list[TodoTask]]:
    return (
        isinstance(value, list)
        and all(isinstance(item, TodoTask) for item in value)
    )


class AgenticLoopPoller:
    """
    Subscriber-driven owner of the agentic turn queue.

    The subscriber is the only source of work. Each event must contain
    exactly one of:

        - unread_chats
        - incomplete_tasks

    The queue controls concurrency and serializes jobs belonging to the
    same session.
    """
    _queue: AgenticTurnQueue
    _subscriber: FollowupCtxSubscriber
    _started: bool

    def __init__(
        self,
        *,
        max_concurrency: int = MAX_CONCURRENCY,
        queue_size: int = QUEUE_SIZE,
    ) -> None:
        self._queue = AgenticTurnQueue(
            max_workers=max_concurrency,
            max_queue_size=queue_size,
        )

        self._subscriber = FollowupCtxSubscriber(self)
        self._started = False

    async def start(self) -> None:
        """
        Start the queue first, then start the subscriber.
        """
        if self._started:
            logger.warning("AgenticLoopPoller already running")
            return

        await self._queue.start()
        self._subscriber.start()

        self._started = True

        logger.info(
            "AgenticLoopPoller started: workers=%d queue_size=%d",
            self._queue.max_workers,
            self._queue.queue.maxsize,
        )

    async def stop(self) -> None:
        """
        Stop the subscriber first so no new jobs are accepted, then stop
        the queue workers.
        """
        if not self._started:
            return

        self._started = False

        try:
            await self._subscriber.stop()
        except Exception:
            logger.exception("Error stopping FollowupCtxSubscriber")

        try:
            await self._queue.stop()
        except Exception:
            logger.exception("Error stopping AgenticTurnQueue")

        logger.info("AgenticLoopPoller stopped")

    async def run_once_from_trigger(
        self,
        event: dict[str, object],
    ) -> None:
        if not self._started:
            logger.warning(
                "AgenticLoopPoller: ignoring event because poller is stopped"
            )
            return

        jobs = update_to_agentic_jobs(event)

        if not jobs:
            logger.debug(
                "AgenticLoopPoller: event produced no agentic jobs"
            )
            return

        for job in jobs:
            session_id = job.get("session_id")
            unread_chats = job.get("unread_chats")
            incomplete_tasks = job.get("incomplete_tasks")

            if not isinstance(session_id, str):
                logger.warning(
                    "AgenticLoopPoller: normalized job has invalid session_id"
                )
                continue

            has_unread_chats = unread_chats is not None
            has_incomplete_tasks = incomplete_tasks is not None

            if has_unread_chats == has_incomplete_tasks:
                logger.warning(
                    "AgenincLoopPoller: normalized job must contain exactly one of unread_chats or incomplete_tasks"
                )
                continue

            if unread_chats is not None and not is_messenger_chat_update_list(unread_chats):
                logger.warning(
                    "AgenticLoopPoller: normalized job has invalid unread_chats"
                )
                continue


            if incomplete_tasks is not None and not is_incomplete_task_list(incomplete_tasks):
                logger.warning(
                    "AgenticLoopPoller: normalized job has invalid incomplete_tasks"
                )
                continue


            queued = await self._queue.submit(
                session_id=session_id,
                unread_chats=unread_chats,
                incomplete_tasks=incomplete_tasks,
            )

            if not queued:
                logger.warning(
                    "Agentic job was not queued: session=%s",
                    session_id,
                )


def is_agentic_loop_poller_running() -> bool:
    return _poller is not None and _is_running


async def start_agentic_loop_poller() -> tuple[bool, str]:
    global _poller
    global _fd
    global _is_running
    global _stop_in_progress

    async with _state_lock:
        if _poller is not None:
            _is_running = True
            return True, "already"

        if _stop_in_progress:
            return False, "stop in progress"

        if not get_telegram_enabled_option():
            return False, "disabled"

        try:
            _fd = os.open(
                _LOCK_PATH,
                os.O_CREAT | os.O_RDWR,
            )

            fcntl.flock(
                _fd,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

        except BlockingIOError:
            if _fd is not None:
                try:
                    os.close(_fd)
                except OSError:
                    pass
                _fd = None

            return False, "another instance is already running (lock)"


        except OSError as exc:
            logger.exception("Unable to acquire poller lock")

            if _fd is not None:
                try:
                    os.close(_fd)
                except OSError:
                    pass

            _fd = None
            return False, str(exc)

        poller: AgenticLoopPoller | None = None

        try:
            _stop_in_progress = False

            poller = AgenticLoopPoller(
                max_concurrency=MAX_CONCURRENCY,
                queue_size=QUEUE_SIZE,
            )

            await poller.start()

            _poller = poller
            _is_running = True

            logger.info("AgenticLoopPoller started successfully")
            return True, "started"

        except Exception as exc:
            logger.exception(
                "Failed to start AgenticLoopPoller"
            )

            if poller is not None:
                try:
                    await poller.stop()
                except Exception:
                    logger.exception(
                        "Failed to stop poller during startup failure"
                    )

            _poller = None
            _is_running = False
            _stop_in_progress = False

            if _fd is not None:
                try:
                    os.close(_fd)
                except OSError:
                    pass

                _fd = None


            return False, str(exc)

async def stop_agentic_loop_poller_async() -> None:
    global _poller
    global _fd
    global _is_running
    global _stop_in_progress

    async with _state_lock:
        if _poller is None:
            _is_running = False
            _stop_in_progress = False
            return

        _stop_in_progress = True
        _is_running = True

        try:
            await _poller.stop()

        except Exception:
            logger.exception(
                "Error stopping AgenticLoopPoller"
            )

        finally:
            _poller = None
            _is_running = False
            _stop_in_progress = False

            if _fd is not None:
                try:
                    os.close(_fd)
                except OSError:
                    pass

            _fd = None


def _stop_agentic_loop_poller_on_exit() -> None:
    """
    Best-effort interpreter-shutdown cleanup.

    Normal application shutdown should call:
        await stop_agentic_loop_poller_async()
    """
    global _poller
    global _fd
    global _is_running

    poller = _poller

    if poller is not None:
        try:
            stop_fn = getattr(poller, "stop", None)

            if stop_fn is not None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop is not None and loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        stop_fn(),
                        loop,
                    )
                    future.result(timeout=3.0)
                else:
                    logger.warning(
                        "Cannot await poller.stop() during interpreter shutdown"
                    )

        except Exception:
            logger.exception(
                "Error stopping AgenticLoopPoller during exit"
            )

    _poller = None
    _is_running = False

    if _fd is not None:
        try:
            os.close(_fd)
        except OSError:
            pass

    _fd = None

async def _run_poller_process() -> None:
    started, reason = await start_agentic_loop_poller()

    if not started:
        if reason == "disabled":
            logger.info("Agentic loop poller is disabled")
            return

        raise RuntimeError(
            f"Failed to start agentic loop poller: {reason}"
        )

    logger.info("Agentic loop poller process is running")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        logger.info("Shutdown requested")
        stop_event.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        signal_number = getattr(signal, signal_name, None)

        if signal_number is not None:
            try:
                loop.add_signal_handler(signal_number, request_shutdown)
            except NotImplementedError:
                # Mainly relevant on Windows.
                pass

    try:
        _ = await stop_event.wait()
    finally:
        logger.info("Stopping agentic loop poller")
        await stop_agentic_loop_poller_async()
        logger.info("Agentic loop poller stopped")


def main() -> None:
    try:
        asyncio.run(_run_poller_process())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()


_ = atexit.register(_stop_agentic_loop_poller_on_exit)
