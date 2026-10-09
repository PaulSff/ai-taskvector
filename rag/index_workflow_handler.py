# runtime/workflow_server_client.py
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from core.normalizer.shared import workflow_inputs_to_json_object
from core.schemas.primitives import JsonObject, WorkflowInputs, WorkflowOutputs
from services.zmq import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

ResponseHandler = Callable[
    [JsonObject],
    Awaitable[None],
]

ErrorHandler = Callable[
    [str, JsonObject],
    Awaitable[None],
]


class WorkflowServerClient:
    def __init__(
        self,
        *,
        pub_endpoint: str,
        sub_endpoint: str,
        response_timeout_s: float = 6000.0,
        topics: ZmqTopics | None = None,
        on_response: ResponseHandler | None = None,
        on_error: ErrorHandler | None = None,
    ) -> None:
        self._topics: ZmqTopics = (
                    topics if topics is not None else ZmqTopics()
                )
        self._pub: ZmqPublisher = ZmqPublisher(
            pub_endpoint=pub_endpoint,
            topics=self._topics,
        )
        self._sub: ZmqSubscriber = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=sub_endpoint,
                topics=[self._topics.result, self._topics.error],
                accept_topics=[self._topics.result, self._topics.error],
            )
        )
        self._sub_endpoint: str = sub_endpoint
        self._response_timeout_s: float = response_timeout_s
        self._on_response: ResponseHandler | None = on_response
        self._on_error: ErrorHandler | None = on_error

        self._futures_by_run_id: dict[str, asyncio.Future[WorkflowOutputs]] = {}
        self._futures_lock: asyncio.Lock = asyncio.Lock()

        self._started: bool = False
        self._start_lock: asyncio.Lock = asyncio.Lock()

        # Register handlers once.
        async def _handle_result(topic: str, payload: JsonObject) -> None:
            await self._handle_result_payload(payload)

        async def _handle_error(topic: str, payload: JsonObject) -> None:
            await self._handle_error_payload(payload)

        self._sub.on(self._topics.result, _handle_result)
        self._sub.on(self._topics.error, _handle_error)

    async def start(self) -> None:
        # Start subscriber once; safe if called concurrently.
        async with self._start_lock:
            if self._started:
                return
            await self._sub.start()
            self._started = True

    async def close(self) -> None:
        async with self._futures_lock:
            for fut in self._futures_by_run_id.values():
                if not fut.done():
                    fut.set_result({"error": "Client shutting down"})
            self._futures_by_run_id.clear()
        # Close the pub socket
        self._pub.close()
        # Stop the subscribers
        await self._sub.stop()
        self._started = False

    async def _get_or_create_future(
        self, run_id: str
    ) -> asyncio.Future[WorkflowOutputs]:
        loop = asyncio.get_running_loop()
        async with self._futures_lock:
            # Normally run_id is unique, but keep it robust.
            fut = self._futures_by_run_id.get(run_id)
            if fut is None or fut.done():
                fut = loop.create_future()
                self._futures_by_run_id[run_id] = fut
            return fut

    async def _pop_future(
        self, run_id: str
    ) -> asyncio.Future[WorkflowOutputs] | None:
        async with self._futures_lock:
            return self._futures_by_run_id.pop(run_id, None)

    async def _handle_result_payload(
        self,
        payload: JsonObject,
    ) -> None:
        run_id = payload.get("run_id")

        if not isinstance(run_id, str):
            return

        fut = await self._pop_future(run_id)
        if fut is None or fut.done():
            return

        result = payload.get("result")
        if isinstance(result, dict):
            fut.set_result({"result": result})
            if self._on_response is not None:
                await self._on_response({"result": result, "payload": payload})
        else:
            fut.set_result({"error": "Missing/invalid `result` key", "payload": payload})

    async def _handle_error_payload(self, payload: JsonObject) -> None:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str):
            return

        fut = await self._pop_future(run_id)
        if fut is None or fut.done():
            return

        err = payload.get("error")
        if not isinstance(err, str):
            err = "Unknown error"

        fut.set_result({"error": err, "payload": payload})

        if self._on_error is not None:
            await self._on_error(err, payload)

    async def run(
        self,
        *,
        workflow_path: str,
        unit_param_overrides: WorkflowInputs,
        initial_inputs: WorkflowInputs | None = None,
        format: str | None = None,
    ) -> WorkflowOutputs:
        """
        Returns:
          - on success: {"result": <raw workflow outputs dict>}
          - on error:   {"error": "<message>", "payload": <raw error payload>}
        """
        await self.start()

        run_id = str(uuid.uuid4())
        fut = await self._get_or_create_future(run_id)

        # Send job request
        self._pub.publish_job(
            run_id=run_id,
            workflow_path=workflow_path,
            initial_inputs=workflow_inputs_to_json_object(initial_inputs),
            unit_param_overrides=workflow_inputs_to_json_object(unit_param_overrides),
            format=format,
            response_endpoint=self._sub_endpoint,
            update_endpoint=None,
        )

        try:
            return await asyncio.wait_for(fut, timeout=self._response_timeout_s)
        except TimeoutError:
            # Ensure we don't leak the future if the timeout hits.
            popped = await self._pop_future(run_id)
            if popped is fut and not fut.done():
                fut.set_result({"error": "Timed out waiting for result", "payload": None})
            return {"error": "Timed out waiting for result", "payload": None}
