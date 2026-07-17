from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import flet as ft

from runtime import ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from gui.components.settings import (
    get_turn_driver_response_endpoint,
    get_turn_driver_update_endpoint,
)
from .progress_overlay import build_progress_overlay

TURN_DRIVER_RESPONSE_ENDPOINT = get_turn_driver_response_endpoint()
TURN_DRIVER_UPDATE_ENDPOINT = get_turn_driver_update_endpoint()

overlay, overlay_show, overlay_hide = build_progress_overlay(
    default_message="Telegram: chating..."
)


class FletZmqHandler(ft.Stack):
    def __init__(self) -> None:
        container = overlay.controls[0]
        super().__init__(expand=True, controls=[container])

        self._overlay_show = overlay_show
        self._overlay_hide = overlay_hide

        self._stop_evt: Optional[asyncio.Event] = None
        self._tasks: list[asyncio.Task[Any]] = []

        self._topics = ZmqTopics()
        self._sub_update: Optional[ZmqSubscriber] = None
        self._sub_response: Optional[ZmqSubscriber] = None

    def did_mount(self) -> None:
        if self._tasks:
            return
        asyncio.get_event_loop().create_task(self._did_mount_async())

    async def _did_mount_async(self) -> None:
        self._stop_evt = asyncio.Event()

        def ensure_dict(payload: Any) -> Any:
            if isinstance(payload, str):
                try:
                    return json.loads(payload)
                except Exception:
                    return None
            return payload

        def extract_telegram_state(msg: dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
            # returns (msg_type, messenger, agent) only when:
            # - msg_type is in_progress/final
            # - messenger exists (same as original gating)
            def maybe_from_msg_wrap(msg_wrap: Any) -> tuple[Optional[str], Optional[str], Optional[str]]:
                if not isinstance(msg_wrap, dict):
                    return None, None, None

                msg_type = msg_wrap.get("type")
                if msg_type not in ("in_progress", "final"):
                    return None, None, None

                inner = msg_wrap.get("message")
                if not isinstance(inner, dict):
                    return None, None, None

                messenger = inner.get("messenger")
                agent = inner.get("agent")
                return msg_type, messenger, agent

            # Case 1 (working on_update shape)
            outer_msg = msg.get("message")
            msg_type, messenger, agent = maybe_from_msg_wrap(outer_msg)
            if msg_type is not None and messenger is not None:
                return msg_type, messenger, agent

            # Orchestrator fallback
            orch = msg.get("orchestrator")
            if isinstance(orch, dict):
                orch_msg = orch.get("message")
                msg_type, messenger, agent = maybe_from_msg_wrap(orch_msg)
                if msg_type is not None and messenger is not None:
                    return msg_type, messenger, agent

                if isinstance(orch_msg, dict):
                    inner = orch_msg.get("message")
                    msg_type, messenger, agent = maybe_from_msg_wrap(inner)
                    if msg_type is not None and messenger is not None:
                        return msg_type, messenger, agent

            # Case 2 (final shape)
            outputs = msg.get("outputs")
            if isinstance(outputs, dict):
                out_orch = outputs.get("orchestrator")
                if isinstance(out_orch, dict):
                    out_orch_msg = out_orch.get("message")
                    msg_type, messenger, agent = maybe_from_msg_wrap(out_orch_msg)
                    if msg_type is not None and messenger is not None:
                        return msg_type, messenger, agent

            return None, None, None

        async def handle_payload(payload: Any) -> None:
            msg = ensure_dict(payload)
            if not isinstance(msg, dict):
                return

            msg_type, messenger, agent = extract_telegram_state(msg)
            if msg_type is None or messenger != "telegram":
                return

            agent_str = agent if agent else "Agent"

            if msg_type == "in_progress":
                self._overlay_show(f"{agent_str}: chatting over Telegram...")
                self.update()
            else:  # "final"
                self._overlay_hide()
                self.update()

        async def on_update(_topic: str, payload: Any) -> None:
            await handle_payload(payload)

        async def on_result(_topic: str, payload: Any) -> None:
            await handle_payload(payload)

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

    def will_unmount(self) -> None:
        if self._stop_evt is not None:
            self._stop_evt.set()

        for t in list(self._tasks):
            t.cancel()

        asyncio.get_event_loop().create_task(self._shutdown_async())

    async def _shutdown_async(self) -> None:
        for sub in (self._sub_update, self._sub_response):
            if sub is not None:
                await sub.stop()
