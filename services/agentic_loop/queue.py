from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from agents.chat.session import create_session
from core.schemas import TodoTask
from messengers_integrations import MessengerChatUpdate
from services.agentic_loop import cfg_helpers as cfg
from services.agentic_loop.run_agentic_loop import run_agentic_loop
from services.logging import setup_colored_logging

DEFAULT_MESSENGER = cfg.default_messenger

MAX_WORKERS = 8
QUEUE_SIZE = 100

logger = setup_colored_logging(logging.INFO)


@dataclass(slots=True)
class AgenticJob:
    """
    A single agentic-loop job.

    Messenger is present for unread-chat jobs and absent for todo jobs.
    Exactly one of unread_chats or incomplete_tasks is populated.
    """

    session_id: str
    messenger: str | None = None
    unread_chats: list[MessengerChatUpdate] | None = None
    incomplete_tasks: list[TodoTask] | None = None

    def __post_init__(self) -> None:
        has_unread_chats = self.unread_chats is not None
        has_incomplete_tasks = self.incomplete_tasks is not None

        if has_unread_chats == has_incomplete_tasks:
            raise ValueError(
                "Exactly one of unread_chats or incomplete_tasks "
                + "must be provided"
            )

        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")

        if has_unread_chats and (
            not isinstance(self.messenger, str)
            or not self.messenger.strip()
        ):
            raise ValueError(
                "messenger must be provided for unread-chat jobs"
            )

        if self.messenger is not None:
            self.messenger = self.messenger.strip()

    @property
    def kind(self) -> str:
        if self.unread_chats is not None:
            return "unread_chats"

        return "incomplete_tasks"

    @property
    def items(self) -> list[MessengerChatUpdate] | list[TodoTask]:
        if self.unread_chats is not None:
            return self.unread_chats

        return self.incomplete_tasks or []


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

        # Worker ID -> currently executing job.
        self._running_jobs: dict[int, AgenticJob] = {}

        self._state_lock: asyncio.Lock = asyncio.Lock()
        self.started: bool = False

    @property
    def running_jobs(self) -> tuple[AgenticJob, ...]:
        """
        Snapshot of jobs currently executing.

        Jobs still waiting in the queue are not included.
        """
        return tuple(self._running_jobs.values())

    @property
    def running_job_count(self) -> int:
        return len(self._running_jobs)

    @property
    def pending_job_count(self) -> int:
        return self.queue.qsize()

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
        Stop immediately.

        Running jobs are cancelled.
        Jobs still waiting in the queue are discarded.
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

        # A cancelled worker may leave jobs pending in the queue.
        # Mark discarded jobs as done so queue.join() cannot hang later.
        while True:
            try:
                _ = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                self.queue.task_done()

        async with self._state_lock:
            self._running_jobs.clear()
            self.session_locks.clear()

        logger.info("Stopped agentic turn queue")

    async def drain_and_stop(self) -> None:
        """
        Finish all queued and currently running jobs, then stop workers.
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

        async with self._state_lock:
            self._running_jobs.clear()
            self.session_locks.clear()

        logger.info("Drained and stopped agentic turn queue")

    async def submit(
        self,
        *,
        session_id: str | None = None,
        messenger: str | None = None,
        unread_chats: list[MessengerChatUpdate] | None = None,
        incomplete_tasks: list[TodoTask] | None = None,
    ) -> bool:
        if (unread_chats is None) == (incomplete_tasks is None):
            raise ValueError(
                "Provide exactly one of unread_chats or incomplete_tasks"
            )

        normalized_session_id = (
            str(session_id).strip()
            if session_id is not None
            else str(uuid.uuid4())
        )

        job = AgenticJob(
            session_id=normalized_session_id,
            messenger=messenger,
            unread_chats=unread_chats,
            incomplete_tasks=incomplete_tasks,
        )

        async with self._state_lock:
            if not self.started:
                raise RuntimeError(
                    "Agentic turn queue has not been started"
                )

            if self._is_duplicate_running_job(job):
                logger.info(
                    "Ignoring duplicate running job: "
                    + "session=%s kind=%s",
                    job.session_id,
                    job.kind,
                )
                return False

            try:
                self.queue.put_nowait(job)
            except asyncio.QueueFull:
                logger.warning(
                    "Agentic queue full; dropping session=%s",
                    job.session_id,
                )
                return False

            logger.info(
                "Queued agentic job: session=%s kind=%s queue_size=%d",
                job.session_id,
                job.kind,
                self.queue.qsize(),
            )

            return True


    def _is_duplicate_running_job(
        self,
        newcomer: AgenticJob,
    ) -> bool:
        return any(
            self._jobs_are_duplicates(newcomer, running_job)
            for running_job in self._running_jobs.values()
        )

    @staticmethod
    def _jobs_are_duplicates(
        left: AgenticJob,
        right: AgenticJob,
    ) -> bool:
        return (
            left.session_id == right.session_id
            and left.kind == right.kind
            and left.items == right.items
        )

    async def get_running_jobs(self) -> list[dict[str, Any]]:
        """
        Return a monitoring-friendly snapshot of active jobs.
        """
        async with self._state_lock:
            return [
                {
                    "worker_id": worker_id,
                    "session_id": job.session_id,
                    "kind": job.kind,
                    "items": job.items,
                }
                for worker_id, job in self._running_jobs.items()
            ]

    async def _worker(self, worker_id: int) -> None:
        while True:
            job = await self.queue.get()

            async with self._state_lock:
                self._running_jobs[worker_id] = job

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
                async with self._state_lock:
                    _ = self._running_jobs.pop(worker_id, None)

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
                "Starting agentic job: worker=%d session=%s kind=%s items=%d",
                worker_id,
                job.session_id,
                job.kind,
                len(job.items),
            )

            session = create_session(job.session_id)

            if job.unread_chats is not None:
                messenger = job.messenger or DEFAULT_MESSENGER

                await run_agentic_loop(
                    session,
                    messenger=messenger,
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
