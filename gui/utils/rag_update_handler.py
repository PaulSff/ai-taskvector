# gui/chat/rag_update_zmq_component.py (name/path is up to you)
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Awaitable, Callable, Optional

from runtime.zmq_messaging import ZmqPublisher, ZmqTopics
from runtime.zmq_subscriber import ZmqSubscriber, ZmqSubscriptionConfig

ResponseHandler = Callable[[dict[str, Any]], Awaitable[None]]
ErrorHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class RagUpdateViaZmq:
    """
    Transport-only component for triggering rag_update via ZMQ:
    - PUB job to the workflow runner
    - SUB to response/error topics
    - invokes hooks and then shuts down
    """

    def __init__(
        self,
        *,
        pub_endpoint: str,
        sub_endpoint: str,
        response_timeout_s: float = 6000.0,
        topics: ZmqTopics = ZmqTopics(),
        on_response: Optional[ResponseHandler] = None,
        on_error: Optional[ErrorHandler] = None,
    ) -> None:
        self._topics = topics
        self._pub = ZmqPublisher(pub_endpoint=pub_endpoint, topics=topics)
        self._sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=sub_endpoint,
                topics=[topics.result, topics.error],
                # Accept topics explicitly to avoid handler surprises.
                accept_topics=[topics.result, topics.error],
            )
        )
        self._response_timeout_s = response_timeout_s
        self._on_response = on_response
        self._on_error = on_error
        self._sub_endpoint = sub_endpoint

        self._run_id: Optional[str] = None
        self._result_future: Optional[asyncio.Future[dict[str, Any]]] = None

        async def _handle_result(topic: str, payload: dict[str, Any]) -> None:
            await self._handle_result_payload(payload)

        async def _handle_error(topic: str, payload: dict[str, Any]) -> None:
            await self._handle_error_payload(payload)

        self._sub.on(self._topics.result, _handle_result)
        self._sub.on(self._topics.error, _handle_error)

    async def _handle_result_payload(self, payload: dict[str, Any]) -> None:
        # Expect: {"run_id": "...", "outputs": {...}, "ts": ...}
        if self._run_id is not None and payload.get("run_id") != self._run_id:
            return
        outputs = payload.get("outputs") if isinstance(payload, dict) else None
        if not isinstance(outputs, dict):
            # Keep it consistent with "unchanged structure is under response key":
            # here we don't have response yet; propagate error via exception-like behavior.
            await self._set_error_from_payload("Malformed result payload", payload)
            return

        # The runner’s result is expected to be available under `response` key.
        response = outputs.get("response") if isinstance(outputs, dict) else None
        if self._result_future is not None and not self._result_future.done():
            self._result_future.set_result({"response": response, "outputs": outputs})
        if self._on_response is not None:
            # GUI hook gets the response-wrapper; caller can extract `response`
            await self._on_response({"response": response, "outputs": outputs})

    async def _handle_error_payload(self, payload: dict[str, Any]) -> None:
        if self._run_id is not None and payload.get("run_id") != self._run_id:
            return
        err = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(err, str):
            err = "Unknown error"
        await self._set_error_from_payload(err, payload)

    async def _set_error_from_payload(self, err: str, payload: dict[str, Any]) -> None:
        if self._result_future is not None and not self._result_future.done():
            self._result_future.set_result({"error": err, "payload": payload})
        if self._on_error is not None:
            await self._on_error(err, payload)

    async def run(
        self,
        *,
        workflow_path: str,
        unit_param_overrides: dict[str, Any],
        initial_inputs: Optional[dict[str, Any]] = None,
        format: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Returns:
          - on success: {"response": <rag_update output dict>, "outputs": <raw outputs>}
          - on error:   {"error": "<message>", "payload": <raw error payload>}
        """
        self._run_id = str(uuid.uuid4())
        self._result_future = asyncio.get_running_loop().create_future()

        await self._sub.start()
        try:
            self._pub.publish_job(
                run_id=self._run_id,
                workflow_path=workflow_path,
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                format=format,
                response_endpoint=None,  # self._sub_endpoint,
                update_endpoint=None,
            )

            result = await asyncio.wait_for(
                self._result_future,
                timeout=self._response_timeout_s,
            )
            return result
        finally:
            # Shut down subscription loop/socket cleanly.
            await self._sub.stop()

    async def close(self) -> None:
        # If you want explicit cleanup, call this; publisher sockets are kept by design.
        await self._sub.stop()
