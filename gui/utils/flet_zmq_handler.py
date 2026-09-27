from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import flet as ft

from agents.chat.zmq_jobs_client import RESPONSE_SUB_ENDPOINTS, UPDATE_BATCH_ENDPOINTS
from core.normalizer.normalizer import to_process_graph
from core.schemas.graph_edit_api import SetGraphCallback
from core.schemas.primitives import Data, JsonObject
from gui.components.progress_overlay import build_progress_overlay
from gui.utils.graph_extractor import extract_successful_graph_after
from services.logging import setup_colored_logging
from services.zmq import ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

logger = setup_colored_logging(logging.DEBUG)

overlay, overlay_show, overlay_hide = build_progress_overlay(
    default_message="Telegram: chating..."
)

RagUpdateCallback = Callable[[str], Awaitable[None]]


class FletZmqHandler(ft.Stack):
    def __init__(self) -> None:
        container = overlay.controls[0]
        super().__init__(expand=True, controls=[container])

        self._overlay_show = overlay_show
        self._overlay_hide = overlay_hide

        self._stop_evt: asyncio.Event | None = None
        self._tasks: list[asyncio.Task[None]] = []

        self._topics = ZmqTopics()
        self._sub_updates: list[ZmqSubscriber] = []
        self._sub_responses: list[ZmqSubscriber] = []

        # RAG trigger plumbing
        self._rag_update_cb: RagUpdateCallback | None = None
        self._rag_update_evt: asyncio.Event | None = None
        self._rag_update_task: asyncio.Task[None] | None = None
        self._rag_update_lock = asyncio.Lock()

        # Set graph from the update message
        self._set_graph_cb: SetGraphCallback | None = None

        # Turn ids in progress to track
        self._turn_seen_in_progress: set[str] = set()
        self._turn_seen_final: set[str] = set()


    def set_graph_callback(self, cb: SetGraphCallback) -> None:
        self._set_graph_cb = cb

    def set_rag_update_callback(self, cb: RagUpdateCallback) -> None:
        self._rag_update_cb = cb

    def did_mount(self) -> None:
        if self._tasks:
            return
        asyncio.get_event_loop().create_task(self._did_mount_async())

    async def _did_mount_async(self) -> None:
        self._stop_evt = asyncio.Event()
        self._rag_update_evt = asyncio.Event()

        def apply_graph_update(msg: Data) -> None:
            graph_after = extract_successful_graph_after(msg)

            if graph_after is None:
                return

            graph_cb = self._set_graph_cb

            if graph_cb is None:
                return

            try:
                graph = to_process_graph(
                    graph_after,
                    format="dict",
                )

            except (TypeError, ValueError, KeyError) as err:
                logger.warning(
                    "Ignoring invalid graph from update message: %s",
                    err,
                )
                return

            try:
                # Apply every valid graph update.
                graph_cb(graph)

            except (RuntimeError, OSError, ValueError, TypeError):
                logger.exception(
                    "Failed to apply graph from update message"
                )

        def ensure_dict(payload: JsonObject) -> object:
            if isinstance(payload, str):
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    return None
            return payload

        def extract_turn_state(msg: Data) -> tuple[str | None, str | None, str | None, str | None]:
            # returns (msg_type, messenger, agent, turn_id)

            def maybe_from_msg_wrap(msg_wrap: object) -> tuple[str | None, str | None, str | None, str | None]:
                if not isinstance(msg_wrap, dict):
                    return None, None, None, None

                msg_type = msg_wrap.get("type")
                if msg_type not in ("in_progress", "final"):
                    return None, None, None, None

                inner = msg_wrap.get("message")
                if not isinstance(inner, dict):
                    return None, None, None, None

                messenger = inner.get("messenger")
                agent = inner.get("agent")
                turn_id = inner.get("turn_id")
                return msg_type, messenger, agent, turn_id

            outer_msg = msg.get("message")
            msg_type, messenger, agent, turn_id = maybe_from_msg_wrap(outer_msg)
            if msg_type is not None and messenger is not None:
                return msg_type, messenger, agent, turn_id

            orch = msg.get("orchestrator")
            if isinstance(orch, dict):
                orch_msg = orch.get("message")
                msg_type, messenger, agent, turn_id = maybe_from_msg_wrap(orch_msg)
                if msg_type is not None and messenger is not None:
                    return msg_type, messenger, agent, turn_id

                if isinstance(orch_msg, dict):
                    inner = orch_msg.get("message")
                    msg_type, messenger, agent, turn_id = maybe_from_msg_wrap(inner)
                    if msg_type is not None and messenger is not None:
                        return msg_type, messenger, agent, turn_id

            outputs = msg.get("outputs")
            if isinstance(outputs, dict):
                out_orch = outputs.get("orchestrator")
                if isinstance(out_orch, dict):
                    out_orch_msg = out_orch.get("message")
                    msg_type, messenger, agent, turn_id = maybe_from_msg_wrap(out_orch_msg)
                    if msg_type is not None and messenger is not None:
                        return msg_type, messenger, agent, turn_id

            return None, None, None, None


        async def handle_payload(payload: JsonObject) -> None:
            msg = ensure_dict(payload)

            if not isinstance(msg, dict):
                return

            msg_type, messenger, agent, turn_id = extract_turn_state(msg)

            logger.info(
                "[FletZmqHandler] Turn state: type=%r, messenger=%r, agent=%r, turn_id=%r",
                msg_type,
                messenger,
                agent,
                turn_id,
            )

            if msg_type is None or messenger != "telegram" or turn_id is None:
                return

            agent_str = agent if agent else "Agent"

            if msg_type == "in_progress":
                if turn_id in self._turn_seen_final:
                    return

                is_new_turn = turn_id not in self._turn_seen_in_progress
                if is_new_turn:
                    self._turn_seen_in_progress.add(turn_id)
                    self._overlay_show(f"{agent_str}: working...")
                    self.update()

                return

            # final
            self._overlay_hide()
            self.update()

            if turn_id not in self._turn_seen_final:
                self._turn_seen_final.add(turn_id)
                self._turn_seen_in_progress.discard(turn_id)

                if self._rag_update_evt is not None:
                    self._rag_update_evt.set()


        async def on_update(
            _topic: str,
            payload: JsonObject,
        ) -> None:
            try:
                msg = ensure_dict(payload)

                if not isinstance(msg, dict):
                    return

                logger.info("[FletZmqHandler] Update received: topic=%s", _topic)

                await handle_payload(msg)
                apply_graph_update(msg)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unhandled exception in update callback")


        async def on_result(
            _topic: str,
            payload: JsonObject,
        ) -> None:
            try:
                msg = ensure_dict(payload)

                if not isinstance(msg, dict):
                    return

                logger.info("[FletZmqHandler] Result received: topic=%s", _topic)

                await handle_payload(msg)
                apply_graph_update(msg)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unhandled exception in response callback")


        self._sub_updates = []
        for endpoint in UPDATE_BATCH_ENDPOINTS:
            sub = ZmqSubscriber(
                config=ZmqSubscriptionConfig(
                    sub_endpoint=endpoint,
                    topics=(self._topics.update_batch,),
                    accept_topics=None,
                    rcvtimeo_ms=200,
                )
            )
            sub.on(self._topics.update_batch, on_update)
            self._sub_updates.append(sub)


        self._sub_responses = []
        for endpoint in RESPONSE_SUB_ENDPOINTS:
            sub = ZmqSubscriber(
                config=ZmqSubscriptionConfig(
                    sub_endpoint=endpoint,
                    topics=(self._topics.result,),
                    accept_topics=None,
                    rcvtimeo_ms=200,
                )
            )
            sub.on(self._topics.result, on_result)
            self._sub_responses.append(sub)

        async def rag_worker() -> None:
            assert self._rag_update_evt is not None
            while True:
                await self._rag_update_evt.wait()
                self._rag_update_evt.clear()

                cb = self._rag_update_cb
                if cb is None:
                    continue

                # avoid overlapping indexing
                async with self._rag_update_lock:
                    # run only if still scheduled (defensive)
                    try:
                        await cb("turn_final")
                    except asyncio.CancelledError:
                        raise
                    except (TimeoutError, OSError, RuntimeError, ValueError, TypeError):
                        # keep UI responsive; indexing errors should be handled by cb if needed
                        pass

        async def run_until_stopped() -> None:
            assert self._stop_evt is not None
            await self._stop_evt.wait()

        self._tasks.append(asyncio.create_task(rag_worker()))

        for sub in self._sub_updates + self._sub_responses:
            self._tasks.append(asyncio.create_task(sub.start()))

        self._tasks.append(asyncio.create_task(run_until_stopped()))

    def will_unmount(self) -> None:
        if self._stop_evt is not None:
            self._stop_evt.set()

        for t in list(self._tasks):
            t.cancel()

        asyncio.get_event_loop().create_task(self._shutdown_async())

    async def _shutdown_async(self) -> None:
        for sub in self._sub_updates + self._sub_responses:
            await sub.stop()
