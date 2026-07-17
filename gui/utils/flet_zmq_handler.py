from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import flet as ft

from runtime import ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from gui.components.settings import (
    get_turn_driver_response_endpoint,
    get_turn_driver_update_endpoint,
)
from .progress_overlay import build_progress_overlay

logger = logging.getLogger(__name__)

TURN_DRIVER_RESPONSE_ENDPOINT = get_turn_driver_response_endpoint()
TURN_DRIVER_UPDATE_ENDPOINT = get_turn_driver_update_endpoint()

# Build overlay ONCE here (no duplication inside the class)
overlay, overlay_show, overlay_hide = build_progress_overlay(
    default_message="Telegram: chtting..."
)

class FletZmqHandler(ft.Stack):
    def __init__(self) -> None:
        # overlay is a module-level ft.Stack from build_progress_overlay()
        container = overlay.controls[0]  # same container object the closures update
        super().__init__(expand=True, controls=[container])

        self._overlay_show = overlay_show
        self._overlay_hide = overlay_hide

        self._stop_evt: Optional[asyncio.Event] = None
        self._tasks: list[asyncio.Task[Any]] = []

        self._topics = ZmqTopics()
        self._sub_update: Optional[ZmqSubscriber] = None
        self._sub_response: Optional[ZmqSubscriber] = None

    def did_mount(self) -> None:
        logger.info("FletZmqHandler.did_mount: entered")

        # Ensure we only start once per instance
        if self._tasks:
            logger.info("FletZmqHandler.did_mount: already started")
            return

        # Schedule the async start logic from the sync lifecycle hook
        asyncio.get_event_loop().create_task(self._did_mount_async())

    async def _did_mount_async(self) -> None:
        self._stop_evt = asyncio.Event()

        def is_telegram_in_progress(msg: Dict[str, Any]) -> bool:
            return msg["type"] == "in_progress" and msg["message"].get("messenger") == "telegram"

        def is_telegram_final(msg: Dict[str, Any]) -> bool:
            return msg["type"] == "final" and msg["message"].get("messenger") == "telegram"

        async def handle_payload(payload: Any) -> None:
            import json

            msg: Any = payload
            if isinstance(payload, str):
                try:
                    msg = json.loads(payload)
                except Exception:
                    logger.exception("FletZmqHandler: json decode failed")
                    return

            if not isinstance(msg, dict):
                logger.info(
                    "FletZmqHandler: ignoring non-dict msg payload_type=%s",
                    type(msg).__name__,
                )
                return

            def _maybe_telegram_state_from_msg_wrap(msg_wrap: Any) -> tuple[Optional[str], Optional[str]]:
                if not isinstance(msg_wrap, dict):
                    return None, None
                msg_type = msg_wrap.get("type")
                if msg_type not in ("in_progress", "final"):
                    return None, None
                inner = msg_wrap.get("message")
                if not isinstance(inner, dict):
                    return None, None
                messenger = inner.get("messenger")
                return msg_type, messenger

            # -----------------------------
            # Preserve your original logic
            # -----------------------------
            msg_type: Optional[str] = None
            messenger: Optional[str] = None

            # 1) Original format: msg["message"] -> {type, message: {messenger,...}}
            outer_msg = msg.get("message")
            msg_type, messenger = _maybe_telegram_state_from_msg_wrap(outer_msg)

            # 2) Fallback: orchestrator-only extraction (no debug unit)
            if msg_type is None:
                orch = msg.get("orchestrator")
                if isinstance(orch, dict):
                    orch_msg = orch.get("message")
                    msg_type, messenger = _maybe_telegram_state_from_msg_wrap(orch_msg)

                    if msg_type is None and isinstance(orch_msg, dict):
                        # Sometimes: orchestrator.message.message -> {type, message: {...}}-like
                        inner = orch_msg.get("message")
                        msg_type, messenger = _maybe_telegram_state_from_msg_wrap(inner)

            # -----------------------------
            # Add ONLY the new shape here
            # (after Case 1 fails)
            # -----------------------------
            if msg_type is None or messenger is None:
                outputs = msg.get("outputs")
                if isinstance(outputs, dict):
                    out_orch = outputs.get("orchestrator")
                    if isinstance(out_orch, dict):
                        out_orch_msg = out_orch.get("message")  # should be the wrap
                        msg_type, messenger = _maybe_telegram_state_from_msg_wrap(out_orch_msg)

            if msg_type is None or messenger is None:
                logger.info(
                    "FletZmqHandler: ignoring msg (no recognizable telegram state). top_keys=%s",
                    list(msg.keys()),
                )
                return

            logger.info("FletZmqHandler: parsed msg type=%s messenger=%s", msg_type, messenger)

            if messenger != "telegram":
                logger.info("FletZmqHandler: ignoring msg messenger=%s (want telegram)", messenger)
                return

            try:
                visible_before = getattr(self.controls[0], "visible", None)
            except Exception:
                visible_before = None

            if msg_type == "in_progress":
                logger.info("FletZmqHandler: calling overlay_show (visible_before=%s)", visible_before)
                self._overlay_show("Telegram: responding...")
                self.update()
            else:  # "final"
                logger.info("FletZmqHandler: calling overlay_hide (visible_before=%s)", visible_before)
                self._overlay_hide()
                self.update()


        async def on_update(_topic: str, payload: Dict[str, Any]) -> None:
            logger.info("FletZmqHandler.on_update: topic=%s payload_type=%s", _topic, type(payload).__name__)
            try:
                await handle_payload(payload)
            except Exception:
                logger.exception("FletZmqHandler: error in update handler")

        async def on_result(_topic: str, payload: Dict[str, Any]) -> None:
            logger.info("FletZmqHandler.on_result: topic=%s payload_type=%s", _topic, type(payload).__name__)
            try:
                await handle_payload(payload)
            except Exception:
                logger.exception("FletZmqHandler: error in result handler")

        logger.info("FletZmqHandler: creating subscribers")

        self._sub_update = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=TURN_DRIVER_UPDATE_ENDPOINT,
                topics=(self._topics.update_batch,),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )
        self._sub_update.on(self._topics.update_batch, on_update)

        self._sub_response = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=TURN_DRIVER_RESPONSE_ENDPOINT,
                topics=(self._topics.result,),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )
        self._sub_response.on(self._topics.result, on_result)

        async def run_until_stopped() -> None:
            assert self._stop_evt is not None
            await self._stop_evt.wait()

        self._tasks.append(asyncio.create_task(self._sub_update.start()))
        self._tasks.append(asyncio.create_task(self._sub_response.start()))
        self._tasks.append(asyncio.create_task(run_until_stopped()))
        logger.info("FletZmqHandler: subscribers started")

    def will_unmount(self) -> None:
        logger.info("FletZmqHandler.will_unmount: entered")

        if self._stop_evt is not None:
            self._stop_evt.set()

        for t in list(self._tasks):
            try:
                t.cancel()
            except Exception:
                pass

        asyncio.get_event_loop().create_task(self._shutdown_async())

    async def _shutdown_async(self) -> None:
        for sub in (self._sub_update, self._sub_response):
            try:
                if sub is not None:
                    await sub.stop()
            except Exception:
                logger.exception("FletZmqHandler: error stopping subscriber")
