"""
The resulting structure is:

AgenincLoopPoller
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
The subscriber payload should provide the session context directly, for example:
{
    "session_id": "chat-or-session-id",
    "unread_chats": [...],
}

or

{
    "todo_list_id": "todo-list-id",
    "incomplete_tasks": [...],
}
"""
from __future__ import annotations

import asyncio
import atexit
import fcntl
import logging
import os
from typing import TypeGuard

from agents.agentic_loop import cfg_helpers as cfg
from core.schemas import TodoTask
from gui.components.settings import get_telegram_enabled_option
from messengers_integrations import MessengerChat
from services.logging import setup_colored_logging

from .follow_up_ctx_subscriber import FollowupCtxSubscriber
from .queue import AgenticTurnQueue

MAX_CONCURRENCY = cfg.default_max_concurrency
QUEUE_SIZE = 100
_LOCK_PATH = cfg.lock_file_path

logger = setup_colored_logging(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

_fd: int | None = None
_poller: AgenincLoopPoller | None = None
_is_running = False
_stop_in_progress = False
_state_lock = asyncio.Lock()


def _get_payload(event: dict[str, object]) -> dict[str, object]:
    """
    Normalize a subscriber event.

    Supported event shapes include:

        {
            "session_id": "session-1",
            "unread_chats": [...],
        }

    and:

        {
            "todo_list_id": "todo-list-1",
            "incomplete_tasks": [...],
        }

    A nested `update` dictionary is also supported.
    """
    update = event.get("update")

    if isinstance(update, dict):
        return update

    return event


def _get_session_id(payload: dict[str, object]) -> str | None:
    """
    Resolve the session identifier supplied by the subscriber.

    For unread messages, session_id is preferred. For todo work,
    todo_list_id is used as the session key.
    """
    value = (
        payload.get("session_id")
        or payload.get("session")
        or payload.get("todo_list_id")
    )

    if value is None:
        return None

    return str(value)


def is_messenger_chat(value: object) -> TypeGuard[MessengerChat]:
    if not isinstance(value, dict):
        return False

    # Replace these fields with the actual required MessengerChat keys.
    return (
        isinstance(value.get("id"), str)
        and isinstance(value.get("session_id"), str)
        and isinstance(value.get("message"), str)
    )

def is_messenger_chat_list(
    value: object,
) -> TypeGuard[list[MessengerChat]]:
    return (
        isinstance(value, list)
        and all(is_messenger_chat(item) for item in value)
    )

def is_incomplete_task_list(
    value: object,
) -> TypeGuard[list[TodoTask]]:
    return (
        isinstance(value, list)
        and all(isinstance(item, TodoTask) for item in value)
    )


class AgenincLoopPoller:
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
            logger.warning("AgenincLoopPoller already running")
            return

        await self._queue.start()
        self._subscriber.start()

        self._started = True

        logger.info(
            "AgenincLoopPoller started: workers=%d queue_size=%d",
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

        logger.info("AgenincLoopPoller stopped")

    async def run_once_from_trigger(
        self,
        event: dict[str, object],
    ) -> None:
        """
        Receive one subscriber event and enqueue one agentic job.

        No agentic loop is run directly from this callback.
        """
        if not self._started:
            logger.warning(
                "Ignoring subscriber event because poller is stopped"
            )
            return

        payload = _get_payload(event)

        unread_chats = payload.get("unread_chats")
        incomplete_tasks = payload.get("incomplete_tasks")

        has_unread_chats = (
            isinstance(unread_chats, list)
            and bool(unread_chats)
        )

        has_incomplete_tasks = (
            isinstance(incomplete_tasks, list)
            and bool(incomplete_tasks)
        )

        # Exactly one work type must be present.
        if has_unread_chats == has_incomplete_tasks:
            logger.warning(
                "Ignoring subscriber event: expected exactly one of unread_chats or incomplete_tasks"
            )
            return

        session_id = _get_session_id(payload)

        if session_id is None:
            logger.error(
                "Ignoring subscriber event: missing session_id or todo_list_id"
            )
            return

        if is_messenger_chat_list(unread_chats) and unread_chats:
            queued = await self._queue.submit(
                session_id=session_id,
                unread_chats=unread_chats,
                incomplete_tasks=None,
            )

        elif is_incomplete_task_list(incomplete_tasks) and incomplete_tasks:
            queued = await self._queue.submit(
                session_id=session_id,
                unread_chats=None,
                incomplete_tasks=incomplete_tasks,
            )

        else:
            logger.warning(
                "Ignoring subscriber event: expected exactly one of unread_chats or incomplete_tasks"
            )
            return


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

        poller: AgenincLoopPoller | None = None

        try:
            _stop_in_progress = False

            poller = AgenincLoopPoller(
                max_concurrency=MAX_CONCURRENCY,
                queue_size=QUEUE_SIZE,
            )

            await poller.start()

            _poller = poller
            _is_running = True

            logger.info("AgenincLoopPoller started successfully")
            return True, "started"

        except Exception as exc:
            logger.exception(
                "Failed to start AgenincLoopPoller"
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
                "Error stopping AgenincLoopPoller"
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
                "Error stopping AgenincLoopPoller during exit"
            )

    _poller = None
    _is_running = False

    if _fd is not None:
        try:
            os.close(_fd)
        except OSError:
            pass

    _fd = None


_ = atexit.register(_stop_agentic_loop_poller_on_exit)
