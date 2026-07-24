# runtime/zmq_subscriber.py
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

import zmq

logger = logging.getLogger("zmq_subscriber")


RecvHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class ZmqSubscriptionConfig:
    sub_endpoint: str
    topics: Iterable[str]
    accept_topics: Optional[Iterable[str]] = None
    rcvtimeo_ms: int = 1000
    max_in_flight_handlers: int = 32  # safe default


class ZmqSubscriber:
    """
    Generic SUB loop:
    - one instance per endpoint/socket
    - JSON-decodes message payloads
    - dispatches by topic to registered async handlers
    - no business logic; only transport + routing
    """

    def __init__(
        self,
        *,
        config: ZmqSubscriptionConfig,
        context: Optional[zmq.Context] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.config = config
        self._ctx = context or zmq.Context.instance()
        self._loop = loop
        self._handlers: Dict[str, RecvHandler] = {}
        self._catch_all: Optional[RecvHandler] = None

        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None

        self._sock: Optional[zmq.Socket] = None
        self._accept_set = (
            set(config.accept_topics) if config.accept_topics is not None else None
        )

    def on(self, topic: str, handler: RecvHandler) -> None:
        if not isinstance(topic, str) or not topic:
            raise ValueError("topic must be a non-empty str")
        self._handlers[topic] = handler

    def on_any(self, handler: RecvHandler) -> None:
        self._catch_all = handler

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task

    def close(self) -> None:
        # safe to call even if not started
        if self._sock is not None:
            try:
                self._sock.close(linger=0)
            except Exception:
                logger.exception("Failed to close ZMQ socket")

    async def _run(self) -> None:
        loop = self._loop or asyncio.get_running_loop()

        tasks_set: set[asyncio.Task[None]] = set()  # <-- fix 2

        try:
            sock = self._ctx.socket(zmq.SUB)
            self._sock = sock  # keep for close()

            sock.connect(self.config.sub_endpoint)

            for t in self.config.topics:
                sock.setsockopt_string(zmq.SUBSCRIBE, t)

            sock.RCVTIMEO = self.config.rcvtimeo_ms

            max_in_flight = int(getattr(self.config, "max_in_flight_handlers", 32))
            max_in_flight = max(1, max_in_flight)
            in_flight_sem = asyncio.Semaphore(max_in_flight)

            def recv_one() -> tuple[str, dict[str, Any]]:
                try:
                    parts = sock.recv_multipart(flags=0)
                except zmq.error.Again:
                    return "", {}

                if not parts:
                    return "", {}

                if len(parts) == 1:
                    topic_b = b""
                    msg_b = parts[0]
                else:
                    topic_b = parts[0]
                    msg_b = parts[1]

                topic_s = topic_b.decode("utf-8", errors="replace") if topic_b else ""

                try:
                    decoded = json.loads(msg_b.decode("utf-8"))
                    if isinstance(decoded, dict):
                        return topic_s, decoded
                    return topic_s, {"_non_dict_payload": decoded}
                except Exception:
                    logger.exception(
                        "JSON decode failed: topic=%s raw_sample=%r",
                        topic_s,
                        msg_b[:200],
                    )
                    return topic_s, {}

            while not self._stop_event.is_set():
                topic, payload = await loop.run_in_executor(None, recv_one)
                if self._stop_event.is_set():
                    break

                if topic == "" and payload == {}:
                    continue

                if self._accept_set is not None and topic not in self._accept_set:
                    continue

                handler = self._handlers.get(topic) or self._catch_all
                if handler is None:
                    continue

                handler_now: RecvHandler = handler  # <-- fix 1 (non-optional)

                async def _run_handler_limited(t: str, p: dict[str, Any]) -> None:
                    async with in_flight_sem:
                        try:
                            await handler_now(t, p)
                        except Exception:
                            logger.exception(
                                "Handler failed: topic=%s payload_keys=%s",
                                t,
                                list(p.keys()) if isinstance(p, dict) else None,
                            )

                task = asyncio.create_task(_run_handler_limited(topic, payload))
                tasks_set.add(task)

                def _on_done(tt: asyncio.Task[None]) -> None:
                    tasks_set.discard(tt)

                task.add_done_callback(_on_done)

        finally:
            if tasks_set:
                await asyncio.gather(*tasks_set, return_exceptions=True)
            self.close()
