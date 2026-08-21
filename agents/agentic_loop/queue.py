from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from agents.agentic_loop.run_agentic_loop import run_agentic_loop
from agents.chat.session import create_session
from core.schemas import TodoTask
from messengers_integrations import MessengerChat
from services.logging import setup_colored_logging

MAX_WORKERS = 8
QUEUE_SIZE = 100

logger = setup_colored_logging(logging.INFO)


@dataclass(slots=True)
class AgenticJob:
    """
    A single agentic-loop job.

    Exactly one of unread_chats or incomplete_tasks should be populated.
    Both job types use the same session_id field.
    """

    session_id: str
    unread_chats: list[MessengerChat] | None = None
    incomplete_tasks: list[TodoTask] | None = None

    def __post_init__(self) -> None:
        has_unread_chats = self.unread_chats is not None
        has_incomplete_tasks = self.incomplete_tasks is not None

        if has_unread_chats == has_incomplete_tasks:
            raise ValueError(
                "Exactly one of unread_chats or incomplete_tasks must be provided"
            )

        if not self.session_id:
            raise ValueError("session_id must not be empty")


class AgenticTurnQueue:
    """
    Bounded queue for agentic-loop jobs.

    Jobs for different session IDs can run concurrently.
    Jobs for the same session ID run sequentially.
    """

    def __init__(
        self,
        *,
        max_workers: int = MAX_WORKERS,
        max_queue_size: int = QUEUE_SIZE,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")

        if max_queue_size < 1:
            raise ValueError("max_queue_size must be at least 1")

        self.max_workers: int = max_workers
        self.queue: asyncio.Queue[AgenticJob] = asyncio.Queue(
            maxsize=max_queue_size,
        )

        self.workers: list[asyncio.Task[None]] = []
        self.session_locks: dict[str, asyncio.Lock] = {}
        self._state_lock: asyncio.Lock = asyncio.Lock()
        self.started: bool = False

    async def start(self) -> None:
        async with self._state_lock:
            if self.started:
                logger.warning("Agentic turn queue already started")
                return

            self.started = True

            self.workers = [
                asyncio.create_task(
                    self._worker(worker_id),
                    name=f"agentic-worker-{worker_id}",
                )
                for worker_id in range(self.max_workers)
            ]

            logger.info(
                "Started agentic turn queue: workers=%d queue_size=%d",
                self.max_workers,
                self.queue.maxsize,
            )

    async def stop(self) -> None:
        """
        Stop workers immediately.

        Queued jobs that have not started are discarded. Running jobs are
        cancelled. Use drain_and_stop() if queued work must finish.
        """
        async with self._state_lock:
            if not self.started:
                return

            self.started = False
            workers = list(self.workers)
            self.workers.clear()

        for worker in workers:
            _ = worker.cancel()

        _ = await asyncio.gather(
            *workers,
            return_exceptions=True,
        )

        self.session_locks.clear()

        logger.info("Stopped agentic turn queue")

    async def drain_and_stop(self) -> None:
        """
        Finish all queued jobs, then stop the workers.
        """
        async with self._state_lock:
            if not self.started:
                return

        await self.queue.join()

        async with self._state_lock:
            self.started = False
            workers = list(self.workers)
            self.workers.clear()

        for worker in workers:
            _ = worker.cancel()

        _ = await asyncio.gather(
            *workers,
            return_exceptions=True,
        )

        self.session_locks.clear()

        logger.info("Drained and stopped agentic turn queue")

    async def submit(
        self,
        *,
        session_id: str | None = None,
        unread_chats: list[MessengerChat] | None = None,
        incomplete_tasks: list[TodoTask] | None = None,
    ) -> bool:
        if (unread_chats is None) == (incomplete_tasks is None):
            raise ValueError(
                "Provide exactly one of unread_chats or incomplete_tasks"
            )

        if not self.started:
            raise RuntimeError(
                "Agentic turn queue has not been started"
            )

        normalized_session_id = (
            str(session_id) if session_id else str(uuid.uuid4())
        )

        job = AgenticJob(
            session_id=normalized_session_id,
            unread_chats=unread_chats,
            incomplete_tasks=incomplete_tasks,
        )

        try:
            self.queue.put_nowait(job)
        except asyncio.QueueFull:
            logger.warning(
                "Agentic queue full; dropping session=%s",
                job.session_id,
            )
            return False

        logger.info(
            "Queued agentic job: session=%s queue_size=%d",
            job.session_id,
            self.queue.qsize(),
        )

        return True

    async def _worker(self, worker_id: int) -> None:
        while True:
            job = await self.queue.get()

            try:
                await self._run_job(job, worker_id)

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Agentic worker failed: worker=%d session=%s",
                    worker_id,
                    job.session_id,
                )

            finally:
                self.queue.task_done()

    async def _run_job(
        self,
        job: AgenticJob,
        worker_id: int,
    ) -> None:
        session_lock = self.session_locks.setdefault(
            job.session_id,
            asyncio.Lock(),
        )

        async with session_lock:
            logger.info(
                "Starting agentic job: worker=%d session=%s",
                worker_id,
                job.session_id,
            )

            session = create_session(job.session_id)

            if job.unread_chats is not None:
                await run_agentic_loop(
                    session,
                    unread_chats=job.unread_chats,
                )
            else:
                await run_agentic_loop(
                    session,
                    incomplete_tasks=job.incomplete_tasks or [],
                )

            logger.info(
                "Completed agentic job: worker=%d session=%s",
                worker_id,
                job.session_id,
            )
