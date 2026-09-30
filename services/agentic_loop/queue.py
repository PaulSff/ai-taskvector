"""
AgenticTurnQueue
├── owns the asyncio queue
├── owns workers
├── owns self.jobs
└── updates job statuses

Callers receive the job ID:

python


job_id = await agentic_queue.submit(
    session_id="session-123",
    incomplete_tasks=tasks,
)

if job_id is None:
    # Duplicate job or queue full
    ...

Examples:
queued_jobs = await agentic_queue.list_jobs(status="queued")
running_jobs = await agentic_queue.list_jobs(status="running")
job = await agentic_queue.get_job(job_id)

"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from agents.chat.session import create_session
from core.schemas import TodoTask
from core.schemas.primitives import Data
from messengers_integrations import MessengerChatUpdate
from services.agentic_loop import cfg_helpers as cfg
from services.agentic_loop.parser import extract_chat_id_from_task_text
from services.agentic_loop.run_agentic_loop import run_agentic_loop
from services.logging import setup_colored_logging

DEFAULT_MESSENGER = cfg.default_messenger

MAX_WORKERS = 8
QUEUE_SIZE = 100

logger = setup_colored_logging(logging.INFO)


JobStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class AgenticJob:
    session_id: str
    messenger: str | None = None
    unread_chats: list[MessengerChatUpdate] | None = None
    incomplete_tasks: list[TodoTask] | None = None
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Runtime metadata
    status: JobStatus = "queued"
    worker_id: int | None = None
    submitted_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        has_unread_chats = self.unread_chats is not None
        has_incomplete_tasks = self.incomplete_tasks is not None

        if has_unread_chats == has_incomplete_tasks:
            raise ValueError(
                "Exactly one of unread_chats or incomplete_tasks must be provided"
            )

        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")

        if has_unread_chats and not isinstance(self.messenger, str):
            raise ValueError(
                "messenger must be provided for unread-chat jobs"
            )

        if self.messenger is not None:
            self.messenger = self.messenger.strip()

    @property
    def kind(self) -> str:
        return (
            "unread_chats"
            if self.unread_chats is not None
            else "incomplete_tasks"
        )

    @property
    def items(self) -> list[MessengerChatUpdate] | list[TodoTask]:
        return (
            self.unread_chats
            if self.unread_chats is not None
            else self.incomplete_tasks or []
        )


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
        # All jobs known to the queue, including queued and completed jobs.
        self.jobs: dict[str, AgenticJob] = {}

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

    @staticmethod
    def _serialize_job(
        job: AgenticJob,
    ) -> Data:
        return {
            "job_id": job.job_id,
            "session_id": job.session_id,
            "kind": job.kind,
            "status": job.status,
            "worker_id": job.worker_id,
            "item_count": len(job.items),
            "submitted_at": job.submitted_at.isoformat(),
            "started_at": (
                job.started_at.isoformat()
                if job.started_at is not None
                else None
            ),
            "finished_at": (
                job.finished_at.isoformat()
                if job.finished_at is not None
                else None
            ),
            "error": job.error,
        }


    async def start(self) -> None:
        async with self._state_lock:
            if self.started:
                logger.warning("AgenticTurnQueue: Already started")
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
                "AgenticTurnQueue: Started workers=%d queue_size=%d",
                self.max_workers,
                self.queue.maxsize,
            )

    async def stop(self) -> None:
        """
        Stop immediately.

        Running jobs are cancelled.
        Jobs still waiting in the queue are discarded and marked cancelled.
        """
        async with self._state_lock:
            if not self.started:
                return

            self.started = False
            workers = list(self.workers)
            self.workers.clear()

        # Cancel workers. Their currently executing jobs should be marked
        # cancelled by _worker's CancelledError handler.
        for worker in workers:
            worker.cancel()

        await asyncio.gather(
            *workers,
            return_exceptions=True,
        )

        # Discard jobs that were still waiting in the queue.
        while True:
            try:
                job = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                async with self._state_lock:
                    job.status = "cancelled"
                    job.finished_at = utc_now()
                    job.error = "Queue stopped before job started"

                self.queue.task_done()

        async with self._state_lock:
            self._running_jobs.clear()
            self.session_locks.clear()

        # Do not clear self.jobs here.
        # This keeps cancelled jobs available through get_job() and list_jobs().

        logger.info("AgenticTurnQueue: Stopped agentic turn queue")


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

        logger.info("AgenticTurnQueue: Drained and stopped agentic turn queue")


    async def submit(
        self,
        *,
        session_id: str | None = None,
        messenger: str | None = None,
        unread_chats: list[MessengerChatUpdate] | None = None,
        incomplete_tasks: list[TodoTask] | None = None,
    ) -> str | None:
        if (unread_chats is None) == (incomplete_tasks is None):
            raise ValueError(
                "Provide exactly one of unread_chats or incomplete_tasks"
            )

        normalized_session_id = (
            str(session_id).strip()
            if session_id is not None
            else str(uuid.uuid4())
        )

        if incomplete_tasks is not None:
            incomplete_tasks = self._filter_incomplete_tasks_for_running_unread_chats(
                incomplete_tasks
            )
            if not incomplete_tasks:
                logger.info(
                    "AgenticTurnQueue: Dropping incomplete-task job after filtering: session=%s",
                    normalized_session_id,
                )
                return None

        job = AgenticJob(
            job_id=str(uuid.uuid4()),
            session_id=normalized_session_id,
            messenger=messenger,
            unread_chats=unread_chats,
            incomplete_tasks=incomplete_tasks,
            status="queued",
            worker_id=None,
            submitted_at=utc_now(),
            started_at=None,
            finished_at=None,
            error=None,
        )

        async with self._state_lock:
            if not self.started:
                raise RuntimeError(
                    "Agentic turn queue has not been started"
                )

            if self._is_duplicate_running_job(job):
                logger.debug(
                    "AgenticTurnQueue: Ignoring duplicate running job: session=%s kind=%s",
                    job.session_id,
                    job.kind,
                )
                return None

            try:
                self.queue.put_nowait(job)
            except asyncio.QueueFull:
                logger.warning(
                    "AgenticTurnQueue: Agentic queue full; dropping job=%s session=%s",
                    job.job_id,
                    job.session_id,
                )
                return None

            self.jobs[job.job_id] = job

            logger.info(
                "AgenticTurnQueue: Queued agentic job: job=%s session=%s kind=%s queue_size=%d",
                job.job_id,
                job.session_id,
                job.kind,
                self.queue.qsize(),
            )

            return job.job_id

    def _is_duplicate_running_job(
        self,
        newcomer: AgenticJob,
    ) -> bool:
        return any(
            self._jobs_are_duplicates(newcomer, running_job)
            for running_job in self._running_jobs.values()
        )

    async def get_running_jobs(self) -> list[Data]:
        async with self._state_lock:
            return [
                self._serialize_job(job)
                for job in self._running_jobs.values()
            ]

    def _filter_incomplete_tasks_for_running_unread_chats(
        self,
        incomplete_tasks: list[TodoTask],
    ) -> list[TodoTask]:
        """
        In order to avoid handling the same unread chats twice,
        all system tasks that are set to handle this specific chat should be filtered out
        from the incomplete_tasks list. If no incomplete_tasks remain, reject the submit entirelly.
        """
        running_session_ids = {
            job.session_id for job in self._running_jobs.values()
        }

        filtered: list[TodoTask] = []

        for task in incomplete_tasks:
            chat_id = extract_chat_id_from_task_text(task.text)

            if chat_id is not None and chat_id in running_session_ids:
                logger.debug(
                    "AgenticTurnQueue: Skipping task already covered by running unread-chat job: chat_id=%s task_id=%s",
                    chat_id,
                    task.id,
                )
                continue

            filtered.append(task)

        return filtered

    async def get_job(
        self,
        job_id: str,
    ) -> Data | None:
        async with self._state_lock:
            job = self.jobs.get(job_id)

            if job is None:
                return None

            return self._serialize_job(job)

    async def list_jobs(
        self,
        *,
        status: JobStatus | None = None,
    ) -> list[Data]:
        async with self._state_lock:
            jobs = list(self.jobs.values())

            if status is not None:
                jobs = [
                    job
                    for job in jobs
                    if job.status == status
                ]

            jobs.sort(key=lambda job: job.submitted_at)

            return [
                self._serialize_job(job)
                for job in jobs
            ]

    async def _worker(self, worker_id: int) -> None:
        while True:
            job = await self.queue.get()

            async with self._state_lock:
                job.status = "running"
                job.worker_id = worker_id
                job.started_at = utc_now()
                self._running_jobs[worker_id] = job

            try:
                await self._run_job(job, worker_id)

            except asyncio.CancelledError:
                async with self._state_lock:
                    job.status = "cancelled"
                    job.finished_at = utc_now()
                    job.error = "Worker cancelled while job was running"

                raise

            except Exception as exc:
                async with self._state_lock:
                    job.status = "failed"
                    job.finished_at = utc_now()
                    job.error = repr(exc)

                logger.exception(
                    "AgenticTurnQueue: Agentic worker failed: worker=%d job=%s session=%s",
                    worker_id,
                    job.job_id,
                    job.session_id,
                )

            else:
                async with self._state_lock:
                    job.status = "completed"
                    job.finished_at = utc_now()
                    job.error = None

                logger.info(
                    "AgenticTurnQueue: Completed agentic job: worker=%d job=%s session=%s",
                    worker_id,
                    job.job_id,
                    job.session_id,
                )

            finally:
                async with self._state_lock:
                    self._running_jobs.pop(worker_id, None)

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
                "AgenticTurnQueue: Starting agentic job: worker=%d session=%s kind=%s items=%d",
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
                "AgenticTurnQueue: Completed agentic job: worker=%d session=%s",
                worker_id,
                job.session_id,
            )
