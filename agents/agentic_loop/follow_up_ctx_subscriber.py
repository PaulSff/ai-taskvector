import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeGuard

from agents.agentic_loop import cfg_helpers as cfg
from services.zmq import ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

logger = logging.getLogger("follow_up_ctx_subscriber")

ZMQ_TG_UPDATE_SUB_ENDPOINT = cfg.zmq_ctx_update_sub_endpoint


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
    _sub_endpoint: str
    _topic: str
    _stop: asyncio.Event
    _task: asyncio.Task[None] | None

    def __init__(
        self,
        poller: TriggerPoller,
        sub_endpoint: str = ZMQ_TG_UPDATE_SUB_ENDPOINT,
    ) -> None:
        self._poller = poller
        self._sub_endpoint = sub_endpoint
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
            "FollowupCtxSubscriber: starting endpoint=%s topic=%s",
            self._sub_endpoint,
            self._topic,
        )

        subscription_config = ZmqSubscriptionConfig(
            sub_endpoint=self._sub_endpoint,
            topics=[self._topic],
        )

        subscriber: ZmqSubscriberLike = ZmqSubscriber(
            config=subscription_config,
            loop=asyncio.get_running_loop(),
        )

        await subscriber.start()

        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def handler(topic: object, payload: object) -> None:
            del topic

            if is_event_payload(payload):
                queue.put_nowait(payload)

        subscriber.on_any(handler)

        try:
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
            await subscriber.stop()
            logger.info("FollowupCtxSubscriber stopping")
