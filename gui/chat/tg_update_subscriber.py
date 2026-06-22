import asyncio
import logging
from typing import Any, Optional

from runtime import ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

logger = logging.getLogger("tg_update_subscriber")

ZMQ_TG_UPDATE_SUB_ENDPOINT = "tcp://127.0.0.1:5556"


class TgUpdateSubscriber:
    def __init__(self, poller: Any, sub_endpoint: str = ZMQ_TG_UPDATE_SUB_ENDPOINT):
        self._poller = poller
        self._sub_endpoint = sub_endpoint
        self._topic = ZmqTopics.update_batch

        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task and not self._task.done():
            logger.warning("TgUpdateSubscriber already running")
            return
        self._stop.clear()
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        t = getattr(self, "_task", None)
        if isinstance(t, asyncio.Task) and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        logger.info(
            "TgUpdateSubscriber: starting endpoint=%s topic=%s",
            self._sub_endpoint,
            self._topic,
        )

        loop = asyncio.get_running_loop()
        cfg = ZmqSubscriptionConfig(
            sub_endpoint=self._sub_endpoint,
            topics=[self._topic],
        )
        sub = ZmqSubscriber(config=cfg, loop=loop)
        await sub.start()

        q: asyncio.Queue = asyncio.Queue()

        async def _handler(topic: Any, payload: Any) -> None:
            if isinstance(payload, dict):
                q.put_nowait(payload)

        sub.on_any(_handler)

        try:
            while not self._stop.is_set():
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=0.5)
                    logger.info(
                        "TgUpdateSubscriber: received update_batch: keys=%s",
                        list(ev.keys()) if isinstance(ev, dict) else type(ev),
                    )
                    await self._poller.run_once_from_trigger(ev)

                except asyncio.TimeoutError:
                    continue

        except asyncio.CancelledError:
            raise
        finally:
            try:
                await sub.stop()
            except Exception:
                pass
            logger.info("TgUpdateSubscriber stopping")
