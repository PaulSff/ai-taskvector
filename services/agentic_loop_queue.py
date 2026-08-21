from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from agents.agentic_loop import run_agentic_turn
from services.logging import setup_colored_logging

MAX_WORKERS = 8
QUEUE_SIZE = 100

logger = setup_colored_logging(logging.INFO)


@dataclass(slots=True)
class AgenticJob:
    unread_chats: list[dict[str, Any]] | None = None
    incomplete_tasks: list[dict[str, Any]] | None = None

    @property
    def session_id(self) -> str | None:
        if self.unread_chats:
            chat = self.unread_chats[0]
            value = (
                chat.get("session_id")
                or chat.get("chat_id")
                or chat.get("id")
                or chat.get("peer_id")
            )
            return str(value) if value is not None else None

        if self.incomplete_tasks:
            value = self.incomplete_tasks[0].get("todo_list_id")
            return str(value) if value is not None else None

        return None


class AgenticTurnQueue:
    def __init__(
        self,
        *,
        max_workers: int = MAX_WORKERS,
        max_queue_size: int = 100,
    ) -> None:
        self.max_workers = max_workers
        self.queue: asyncio.Queue[AgenticJob] = asyncio.Queue(
            maxsize=max_queue_size,
        )
        self.workers: list[asyncio.Task[None]] = []
        self.started = False

        # Prevent concurrent turns for the same session/chat.
        self.session_locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        if self.started:
            return

        self.started = True
        self.workers = [
            asyncio.create_task(
                self._worker(index),
                name=f"agentic-worker-{index}",
            )
            for index in range(self.max_workers)
        ]

        logger.info(
            "Started agentic turn queue with %d workers",
            self.max_workers,
        )

    async def stop(self) -> None:
        if not self.started:
            return

        self.started = False

        for worker in self.workers:
            worker.cancel()

        _ = await asyncio.gather(
            *self.workers,
            return_exceptions=True,
        )

        self.workers.clear()
        logger.info("Stopped agentic turn queue")

    async def submit(
        self,
        *,
        unread_chats: list[dict[str, Any]] | None = None,
        incomplete_tasks: list[dict[str, Any]] | None = None,
    ) -> bool:
        if (unread_chats is None) == (incomplete_tasks is None):
            raise ValueError(
                "Provide exactly one of unread_chats or incomplete_tasks"
            )

        if not self.started:
            raise RuntimeError("Agentic turn queue has not been started")

        job = AgenticJob(
            unread_chats=unread_chats,
            incomplete_tasks=incomplete_tasks,
        )

        try:
            self.queue.put_nowait(job)
        except asyncio.QueueFull:
            logger.warning(
                "Agentic queue is full; dropping session=%s",
                job.session_id,
            )
            return False

        logger.info(
            "Queued agentic turn: session=%s queue_size=%d",
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
        session_id = job.session_id

        if session_id is None:
            logger.error(
                "Skipping agentic job without session ID: worker=%d",
                worker_id,
            )
            return

        lock = self.session_locks.setdefault(
            session_id,
            asyncio.Lock(),
        )

        # Jobs for different sessions can run concurrently.
        # Jobs for the same session run sequentially.
        async with lock:
            logger.info(
                "Starting agentic job: worker=%d session=%s",
                worker_id,
                session_id,
            )

            await run_agentic_turn(
                unread_chats=job.unread_chats,
                incomplete_tasks=job.incomplete_tasks,
            )

            logger.info(
                "Completed agentic job: worker=%d session=%s",
                worker_id,
                session_id,
            )
