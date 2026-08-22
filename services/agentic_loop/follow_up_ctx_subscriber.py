import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeGuard

from services.agentic_loop import cfg_helpers as cfg
from services.zmq import ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

logger = logging.getLogger("follow_up_ctx_subscriber")

ZMQ_UNREAD_MESSAGES_SUB_ENDPOINT = cfg.zmq_unread_msg_update_sub_endpoint
ZMQ_TODO_SUB_ENDPOINT = cfg.zmq_todo_sub_endpoint


class TriggerPoller(Protocol):
    async def run_once_from_trigger(
        self,
        event: dict[str, object],
    ) -> None:
        ...


class ZmqSubscriberLike(Protocol):
    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    def on_any(
        self,
        handler: Callable[[object, object], Awaitable[None]],
    ) -> None:
        ...


def is_event_payload(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(
        isinstance(key, str) for key in value
    )


class FollowupCtxSubscriber:
    _poller: TriggerPoller
    _sub_endpoints: tuple[str, ...]
    _topic: str
    _stop: asyncio.Event
    _task: asyncio.Task[None] | None

    def __init__(
        self,
        poller: TriggerPoller,
        sub_endpoints: tuple[str, ...] = (
            ZMQ_UNREAD_MESSAGES_SUB_ENDPOINT,
            ZMQ_TODO_SUB_ENDPOINT,
        ),
    ) -> None:
        self._poller = poller
        self._sub_endpoints = sub_endpoints
        self._topic = ZmqTopics.update_batch
        self._stop = asyncio.Event()
        self._task = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            logger.warning("FollowupCtxSubscriber: already running")
            return

        self._stop.clear()
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()

        task = self._task
        if task is not None and not task.done():
            _ = task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

        self._task = None

    async def _run(self) -> None:
        logger.info(
            "FollowupCtxSubscriber: starting endpoints=%s topic=%s",
            self._sub_endpoints,
            self._topic,
        )

        loop = asyncio.get_running_loop()

        subscribers: list[ZmqSubscriberLike] = [
            ZmqSubscriber(
                config=ZmqSubscriptionConfig(
                    sub_endpoint=sub_endpoint,
                    topics=[self._topic],
                ),
                loop=loop,
            )
            for sub_endpoint in self._sub_endpoints
        ]

        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def handler(topic: object, payload: object) -> None:
            del topic

            if is_event_payload(payload):
                queue.put_nowait(payload)

        try:
            for subscriber in subscribers:
                subscriber.on_any(handler)

            _ = await asyncio.gather(
                *(subscriber.start() for subscriber in subscribers)
            )

            while not self._stop.is_set():
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=0.5,
                    )

                    logger.info(
                        "FollowupCtxSubscriber: received update_batch: keys=%s",
                        list(event),
                    )

                    await self._poller.run_once_from_trigger(event)

                except TimeoutError:
                    continue

        finally:
            _ = await asyncio.gather(
                *(subscriber.stop() for subscriber in subscribers),
                return_exceptions=True,
            )

            logger.info("FollowupCtxSubscriber stopping")
